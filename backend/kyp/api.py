import os
import asyncio
from contextlib import suppress
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse
from .operations import SharedOperations
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from .repository import Repository
from .parser import parse_label
from .matcher import match_many, apply_confirmations, ConfirmationRequired
from .ocr import default_provider, OCRUnavailable

class ScanInput(BaseModel):
    product_context: Literal['general', 'food', 'cosmetics'] = 'general'
    parsing_mode: Literal['structured', 'comma_review'] = 'structured'
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=30000)

class IngredientConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    position: int = Field(ge=0, le=199, strict=True)
    confirmation_key: str = Field(min_length=64, max_length=64)
    ingredient_id: str | None = Field(max_length=200)

class ConfirmInput(BaseModel):
    confirmations: list[IngredientConfirmation] = Field(default_factory=list, max_length=200)
    product_context: Literal['general', 'food', 'cosmetics'] = 'general'
    parsing_mode: Literal['structured', 'comma_review'] = 'structured'
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=30000)

class ScanStore:
    def __init__(self):
        self.records = {}
        self.lock = threading.Lock()
    def create(self, confidence=None, parsing_mode="structured"):
        with self.lock:
            instant = time.monotonic()
            self.records = {k:v for k,v in self.records.items() if v[1] > instant}
            if len(self.records) >= 1000:
                raise HTTPException(503, 'Local scan capacity reached; try again later')
            identity, capability = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
            self.records[identity] = (capability, instant + 1800, confidence, parsing_mode)
            return identity, capability
    def authorize(self, identity, capability, include_mode=False):
        with self.lock:
            record = self.records.get(identity)
            if not record or record[1] <= time.monotonic() or not capability or not secrets.compare_digest(record[0], capability):
                raise HTTPException(404, 'Scan not found or expired')
            return (record[2], record[3]) if include_mode else record[2]

def create_app(db_path=None, ocr=None):
    public = os.getenv('KYP_PUBLIC_MODE') == '1'
    origin = os.getenv('KYP_PUBLIC_ORIGIN', '')
    secret = os.getenv('KYP_OPERATION_SECRET', '')
    parsed_origin = urlparse(origin)
    if public and (parsed_origin.scheme != 'https' or not parsed_origin.hostname or parsed_origin.username or parsed_origin.password or parsed_origin.path not in ('', '/') or parsed_origin.query or parsed_origin.fragment or len(secret) < 32 or secret.startswith('REPLACE_')):
        raise ValueError('Public mode requires an HTTPS KYP_PUBLIC_ORIGIN and KYP_OPERATION_SECRET of at least 32 characters')
    @asynccontextmanager
    async def lifespan(app):
        app.state.repository = Repository(db_path or os.getenv('KYP_DATABASE_URL') or os.getenv('KYP_DB', str(Path(__file__).resolve().parents[1] / 'data' / 'kyp.sqlite3')))
        if public:
            if not app.state.repository.postgres:
                raise ValueError('Public mode requires PostgreSQL for shared operations')
            app.state.operations = SharedOperations(app.state.repository, secret)
        async def cleanup_loop():
            while True:
                await run_in_threadpool(app.state.operations.cleanup)
                await asyncio.sleep(60)
        cleanup = asyncio.create_task(cleanup_loop()) if public else None
        try:
            yield
        finally:
            if cleanup:
                cleanup.cancel()
                with suppress(asyncio.CancelledError): await cleanup
    app = FastAPI(title='KYP ingredient lookup', version='0.1.0', lifespan=lifespan)
    scans, provider = ScanStore(), ocr or default_provider()
    ocr_slots = threading.BoundedSemaphore(2)
    if public:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(origin).hostname])

    @app.middleware('http')
    async def privacy_and_limits(request, call_next):
        if public:
            if request.url.scheme != 'https':
                return JSONResponse({'detail':'HTTPS is required'}, status_code=400, headers={'Cache-Control':'no-store'})
            if request.method not in {'GET','POST','HEAD','OPTIONS'}:
                return JSONResponse({'detail':'Method not allowed'}, status_code=405)
            group = 'images' if request.url.path in {'/scans/image','/images/orient'} else 'requests'
            allowed = await run_in_threadpool(app.state.operations.allow, request.client.host if request.client else 'unknown', group, 6 if group == 'images' else 120)
            if not allowed:
                return JSONResponse({'detail':'Too many requests; retry in a minute'},status_code=429,headers={'Retry-After':'60','Cache-Control':'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if public: response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    def scan_store():
        return app.state.operations if public else scans


    def parsed(text, confidence=None, context='general', parsing_mode='structured'):
        try:
            tokens = parse_label(text, confidence, context, comma_review=parsing_mode == "comma_review")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not tokens:
            raise HTTPException(422, 'No ingredients detected')
        return tokens

    def response(text, confidence=None, metadata=None, allow_incomplete=False, context='general', parsing_mode='structured'):
        parse_warning = None
        try:
            tokens = parsed(text, confidence, context, parsing_mode)
        except HTTPException as exc:
            if not allow_incomplete or exc.status_code != 422:
                raise
            # OCR success and parser success are separate states. Never repair
            # uncertain punctuation or discard readable text behind a 422.
            tokens = []
            parse_warning = str(exc.detail)
        review_warning = 'Comma-separated recovery: blend grouping is uncertain. Check every entry against the label, correct it, confirm a candidate or keep it unknown.' if parsing_mode == 'comma_review' else None
        if metadata is not None and not re.search(r'\b(?:ingredients|ingrédients|inci)\b', text, re.I):
            review_warning = 'Ingredient heading not detected. Crop to the ingredient panel and check the extracted text.' 
        identity, capability = scan_store().create(confidence, parsing_mode=parsing_mode)
        return {'id': identity, 'scan_token': capability, 'expires_in_seconds': 1800, 'text': text, 'tokens': [t.to_dict() for t in tokens], 'match_preview': match_many(tokens, app.state.repository, context, review_scope=identity) if tokens else [], 'ocr': metadata, 'review_required': True, 'parse_warning': parse_warning, 'review_warning': review_warning, 'parsing_mode': parsing_mode}

    @app.get('/', include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'stage': 'mvp', 'repository': app.state.repository.backend}

    @app.post('/scans', status_code=201)
    def create_scan(body: ScanInput):
        return response(body.text, context=body.product_context, parsing_mode=body.parsing_mode)

    async def process_image(request, x_image_processing_consent, x_product_context='general', orient=False):
        if x_image_processing_consent != 'yes':
            raise HTTPException(400, 'Explicit consent to server image processing is required')
        if request.headers.get('content-type', '').split(';')[0] not in ('image/jpeg', 'image/png', 'image/webp'):
            raise HTTPException(415, 'Use JPEG, PNG or WebP')
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > 8 * 1024 * 1024:
                raise HTTPException(413, 'Image must be at most 8 MB')
            payload.extend(chunk)
        if not payload:
            raise HTTPException(422, 'Image is empty')
        if not ocr_slots.acquire(blocking=False):
            raise HTTPException(503, 'OCR is busy; retry shortly')
        try:
            if orient:
                if not hasattr(provider, 'orient'):
                    raise OCRUnavailable('Auto orientation is unavailable. Use the rotation controls.')
                return await run_in_threadpool(provider.orient, bytes(payload))
            result = await run_in_threadpool(provider.read, bytes(payload))
            return response(result['text'], result.get('ocr_confidence'), {k:v for k,v in result.items() if k != 'text'}, allow_incomplete=True, context=x_product_context)
        except OCRUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            ocr_slots.release()
            payload.clear()

    @app.post('/images/orient')
    async def orient_image(request: Request, x_image_processing_consent: str | None = Header(default=None)):
        return await process_image(request, x_image_processing_consent, orient=True)

    @app.post('/scans/image', status_code=201)
    async def image_scan(request: Request, x_image_processing_consent: str | None = Header(default=None), x_product_context: Literal['general', 'food', 'cosmetics'] = Header(default='general')):
        return await process_image(request, x_image_processing_consent, x_product_context)

    @app.post('/scans/{identity}/review', status_code=201)
    def rereview(identity: str, body: ScanInput, x_scan_token: str | None = Header(default=None)):
        confidence = scan_store().authorize(identity, x_scan_token)
        return response(body.text, confidence=confidence, context=body.product_context, parsing_mode=body.parsing_mode)

    @app.post('/scans/{identity}/confirm')
    def confirm(identity: str, body: ConfirmInput, x_scan_token: str | None = Header(default=None)):
        confidence, parsing_mode = scan_store().authorize(identity, x_scan_token, include_mode=True)
        if body.parsing_mode != parsing_mode:
            raise HTTPException(422, 'Parsing mode changed. Review the ingredient entries again before lookup.')
        results = match_many(parsed(body.text, confidence=confidence, context=body.product_context, parsing_mode=body.parsing_mode), app.state.repository, body.product_context, review_scope=identity)
        try:
            apply_confirmations(results, [item.model_dump() for item in body.confirmations], app.state.repository, body.product_context)
        except ConfirmationRequired as exc:
            raise HTTPException(409, {'message': str(exc), 'pending_positions': exc.positions}) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'type': 'ingredient_lookup', 'product_context': body.product_context, 'tokens': results, 'matched_count': sum(t['match_status']=='matched' for t in results), 'total_count': len(results)}

    @app.get('/ingredients/{identity}')
    def ingredient(identity: str, product_context: Literal['general', 'food', 'cosmetics'] = 'general'):
        result = app.state.repository.ingredient(identity, context=product_context)
        if not result:
            raise HTTPException(404, 'Ingredient not found')
        return result
    return app

app = create_app()

# KYP — Know Your Product

Understand the ingredients in your food and cosmetic products.

KYP lets you scan an ingredient label, review the extracted text, and explore ingredient descriptions with supporting sources.

## Features

- Scan a label using a camera or uploaded photo.
- Crop and rotate photos before extracting text.
- Review and correct ingredient text.
- Match ingredients against a food and cosmetics catalog.
- Explore ingredient descriptions and source references.
- Use the browser client or the mobile app.

## How it works

1. Choose Food, Cosmetics, or Other / unsure.
2. Upload a label photo or enter ingredient text.
3. Review the text and confirm uncertain matches.
4. View the matched ingredients and available descriptions.

## Built with

- **Backend:** Python and FastAPI
- **Mobile:** React Native and Expo
- **OCR:** On-device text recognition and a Tesseract.js server fallback
- **Database:** SQLite for local development, with PostgreSQL support

## Run locally on macOS

Install **Python 3.14** and **Node.js 24**, then open Terminal in the project folder:

```bash
bash scripts/setup-mac.sh
cd backend
unset KYP_DATABASE_URL KYP_PUBLIC_MODE
.venv/bin/python -B -m uvicorn kyp.api:app --host 127.0.0.1 --port 8001
```

Open **http://127.0.0.1:8001**. API documentation is available at **http://127.0.0.1:8001/docs**.

Ingredient matching requires a populated catalog. See the [Mac setup guide](MACBOOK-SETUP.md) for catalog restoration and fresh setup instructions, and the [mobile guide](mobile/README.md) for running the mobile app.

## Project status

KYP is a development MVP. Ingredient descriptions are source-backed where available; unknown ingredients and unavailable descriptions remain visible for review. OCR results may need correction.

KYP does not currently provide safety scores or medical advice. Matching an ingredient does not establish that a product is safe or unsafe.

## Learn more


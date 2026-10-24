# Stage 1 pilot and device checks

## Device inventory

- Installed Android AVD: automated OCR/review/lookup and compound tests run locally.
- Physical Pixel and Motorola e300: owner reports availability; OS versions and ADB authorization are not yet recorded. `adb devices` currently lists only emulator-5554.
- iOS device/native build: not available in this environment.

## Record for every device

Model, OS/build, app build, API/catalog/matcher versions, test date, tester, original text-scale setting, result and evidence. Restore changed emulator/device settings after testing. Use permitted packaging photos; record consent separately from device permission.

## Test sequence

1. Deny camera permission; verify explanation, retry/settings path and photo/text alternatives. Repeat with permission allowed and cancellation.
2. Photograph and pick labels, crop, rotate all four ways, reset and auto-orient. Ambiguous orientation must stay unchanged. Originals must remain in the photo library.
3. Read a food label and a cosmetic label. Test native OCR success, unreadable output and unavailable OCR. Decline server fallback and verify no image request; accept separately and verify the configured server only.
4. Correct a typo, missing comma and broken bracket. Check nested blend leaves and their parent labels. Change product type and text during requests; old choices/results must disappear.
5. Confirm one suggested ingredient, keep another unknown, leave one pending. Lookup must remain blocked until every flagged ingredient is reviewed. Check detail disclosure, raw wording, nullable probabilities and description/source attribution.
6. Turn network off during review/lookup, retry after reconnect and exercise expired sessions. Corrections must stay editable and stale matches must not return.
7. Check application cache after success, cancellation, replacement and failure; no input image copy should remain after it is no longer needed. Library originals must remain. Include forced-process termination in privacy review; normal cleanup is not evidence of crash cleanup.
8. Test default and enlarged system text, TalkBack/VoiceOver reading order, button names/selected states, keyboard behavior, contrast and touch targets. A passed UI dump or larger-text test is not a screen-reader sign-off.
9. Ask pilot users to explain a matched name, unknown identity, missing description and uncalibrated probability. Record correction effort and source-navigation success separately from matching coverage.

## Locally executed evidence

- Browser: nested food names/descriptions, unknown confirmation guard, keyboard details link, 320px width, network failure and retry.
- Android AVD: nested parent labels, three food descriptions, completed lookup at system font_scale 1.3; setting restored afterward. Screenshot: screenshots/stage1-native-nested-food.png.
- Existing Android AVD smoke covers photo selection/native OCR on a generated synthetic label and cache cleanup. Real camera optics, actual TalkBack behavior and physical-device results remain unverified.

A reviewer must fill actual outcomes and findings; this checklist is not a signed test report.

## Feature verification

For each feature, run the Django suite and the headless Playwright workflow documented under “Visual review” in README.md. Extend qa/visual.py with the affected page, a representative interaction and its resulting state when existing coverage misses the change. Include relevant empty, filled, validation or error states. Use the disposable test household.

Inspect the actual screenshots at desktop and phone sizes in light and dark themes. Check text contrast, control labels and focus, card spacing and alignment, overflow, and the primary action. Fix observed issues and rerun the checks. Report which feature flow was exercised and any unverified behavior.

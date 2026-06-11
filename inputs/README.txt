# Manual signals (copy/paste from Googling)

If Executive Leader finds useful public pages by Googling (articles, press releases, filings, regulatory pages),
you can drop them here so the radar ingests them legally without scraping gated services.

## Option A (recommended): inputs/manual_signals.csv

Minimum column: url

Recommended columns:
- title
- summary
- source (optional; if blank we auto-use the domain like fiercepharma.com)
- published (optional)

Optional columns for better filtering:
lane, account, account_type, region, service_line, topic, tags,
is_partnership, partner_a, partner_b, deal_value, modality, deal_stage, deal_geography

## Option B: inputs/manual_urls.csv

A simpler file with a single column: url
(You can also add title/summary if you want.)

Run RUN_RADAR.bat after adding rows.

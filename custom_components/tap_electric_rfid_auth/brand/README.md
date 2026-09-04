# Brand assets

Flat layout, matching how `home-assistant/brands` itself stores a single
integration's assets:

- `source.png` — master raster (750×750, RGBA, transparent background), only
  used to regenerate the files below if the logo ever changes.
- `icon.png` (256×256), `icon@2x.png` (512×512), `logo.png` (256×256),
  `logo@2x.png` (512×512) — the brand-ready files. `logo.png` is also what
  the project [README](../../../README.md) displays.

Regenerate the four brand-ready files from `source.png` any time it changes:

```bash
py -3.14 -c "
from PIL import Image
src = Image.open('custom_components/tap_electric_rfid_auth/brand/source.png').convert('RGBA')
for name, size in {'icon.png':256,'icon@2x.png':512,'logo.png':256,'logo@2x.png':512}.items():
    src.resize((size, size), Image.LANCZOS).save(f'custom_components/tap_electric_rfid_auth/brand/{name}', 'PNG', optimize=True)
"
```

## Submitting the official HA/HACS icon

Home Assistant and HACS both pull integration icons from the separate
[home-assistant/brands](https://github.com/home-assistant/brands)
repository — nothing inside `custom_components/` is used for that. Until a
PR there is merged, the integration just shows a generic icon in the UI.

To submit:

1. Fork `home-assistant/brands`.
2. Create `custom_integrations/tap_electric_rfid_auth/` (the domain name
   must match `manifest.json`'s `domain` exactly) and copy in `icon.png`,
   `icon@2x.png`, `logo.png`, `logo@2x.png` from this folder.
3. Open a PR. Their CI checks image size/format automatically; a maintainer
   reviews and merges it. This can take a while and isn't something we can
   do from this repo — it has to be a PR against their repo from your own
   GitHub account.

Once merged, `manifest.json`'s `domain` (`tap_electric_rfid_auth`) is all
Home Assistant/HACS need to pick the icon up automatically — no change
needed in this repo.

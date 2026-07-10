# BPS Trade

A local web app and command-line downloader for Indonesian export/import data from the BPS `dataexim` API.

## Web app

1. Obtain a WebAPI key from BPS.
2. Save the key in a file named `.bps_key` in this directory.
3. Start the app:

   ```powershell
   python bps_exim_app.py
   ```

4. Open <http://127.0.0.1:8766> if the browser does not open automatically.

The browser talks only to the local Python server. The BPS API key is read by the backend and is excluded from Git.

## Command line

Run `python bps_exim.py --help` for options. For example:

```powershell
python bps_exim.py get --flow export --hs 01 --year 2023
```

The project uses only the Python standard library. Python 3.10 or newer is recommended.

## Alternative Sites interface

The alternative frontend lives in `site/` and keeps the existing GitHub Pages app in `docs/` unchanged.

```powershell
npm install
npm run dev
```

Use `npm run build` to create the production bundle in `dist/`.

# Deploying the Altis dashboard (Streamlit Community Cloud)

This app is a single Streamlit service (`app.py`) that calls the engine in-process —
there is no separate backend to deploy. Host it on **Streamlit Community Cloud**.

> ⚠️ **Licensed data.** This repo contains real (anonymised) Altis data. Deploy it
> only from a **private** repo, behind the **password gate** (set `APP_PASSWORD`).
> Do not deploy the data from a public repo.

## One-time setup

1. Push this project to a **private** GitHub repo (the deploy source).
2. Go to <https://share.streamlit.io> → **New app** → pick the private repo,
   branch `main`, main file `app.py`.
3. Open **Advanced settings → Secrets** and paste (see `.streamlit/secrets.toml.example`):

   ```toml
   APP_PASSWORD = "the-password-you-give-judges"
   OPENAI_API_KEY = "sk-..."        # optional; enables the LLM mapping backend
   ```

4. **Deploy.** Streamlit installs `requirements.txt` automatically.

## How it behaves

- **Password gate** — active only when `APP_PASSWORD` is set (it is, on the deploy).
  Local runs and the public repo have no password set, so they stay open.
- **OpenAI key** — read from Secrets (bridged into the environment), so the GL
  Mapping panel's `openai` backend works. Without it, the panel uses the keyless
  heuristic. It defaults to the heuristic so cold starts are fast; switch the
  engine to `openai` in the panel when demoing.
- **Data** — "Real data" mode reads the reconciled `data/transactions.csv` +
  the P&L JSON committed in the repo. Both must be present in the deploy repo.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py            # no password unless you add .streamlit/secrets.toml
```

To test the gate locally, copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` and set `APP_PASSWORD`.

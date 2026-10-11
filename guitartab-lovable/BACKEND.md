# Connecting the FastAPI backend

Set `VITE_API_BASE_URL` (default `http://localhost:8000`) in `.env` or your hosting env.

The backend must allow the frontend origin via CORS, e.g.:

```python
app.add_middleware(CORSMiddleware,
  allow_origins=["http://localhost:8080", "https://<your-app>.lovable.app"],
  allow_methods=["*"], allow_headers=["*"])
```

Publishing the frontend does not deploy the Python backend; host it separately over HTTPS
(an https page cannot call an http://localhost API).

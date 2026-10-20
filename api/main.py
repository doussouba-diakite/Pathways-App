from fastapi import FastAPI

app = FastAPI(title="Pathways API")


@app.get("/health")
def health():
        return {"status": "ok"}

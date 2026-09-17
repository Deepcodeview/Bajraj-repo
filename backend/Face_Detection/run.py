"""
run.py — Start Face Recognition API server
"""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8001, reload=True)

import uvicorn

if __name__ == "__main__":
    print("Starting Context Engine API on port 8001...")
    uvicorn.run("data.api:app", host="127.0.0.1", port=8001, reload=True)

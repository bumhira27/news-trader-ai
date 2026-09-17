import uvicorn
import os

if __name__ == "__main__":
    print("Starting lightweight unified API server on port 8001...")
    
    # Ensure it uses SQLite by default
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///economic_data.db"

    # Start the server on port 8001 (so the C# bot can connect)
    uvicorn.run("economic_data_server.app.main:app", host="127.0.0.1", port=8001, reload=True)

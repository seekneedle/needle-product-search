from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from data.task import TaskEntry 
from data.database import Base  
from server.server import app
import threading
import time
import uvicorn
from fastapi.testclient import TestClient
# Database setup
DATABASE_URL = "sqlite:///res/example.db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def run_app():
    """Function to run the FastAPI app using uvicorn."""
    uvicorn.run(app, host="127.0.0.1", port=8000)

def before_all(context):
    # Setup code before all tests run
    # Create the database tables
    Base.metadata.create_all(engine)

    # Start the FastAPI app in a separate thread
    context.server_thread = threading.Thread(target=run_app)
    context.server_thread.start()

    # Give the server a moment to start
    time.sleep(2)
    # Setup the application
    context.client = TestClient(app) 
    
    # Populate mock_tasks with realistic data
    task0 = TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174000",
            status="RUNNING"
    )
    task0.save()
    task1 = TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174001",
            status="SUCCESS"
    )
    task1.save()
    task2 = TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174002",
            status="FAIL"
    )
    task2.save()
"""
    with Session() as session:
        mock_tasks = []
        mock_tasks.append(TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174000",
            status="RUNNING"
        ))
        mock_tasks.append(TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174001",
            status="SUCCESS"
        ))
        mock_tasks.append(TaskEntry(
            task_id="123e4567-e89b-12d3-a456-426614174002",
            status="FAIL"
        ))

        session.add_all(context.mock_tasks)
        session.commit() 
        
"""

def after_all(context):
    # Cleanup code after all tests run
    
    # Remove all mock data from the database
    with Session() as session:
        session.query(TaskEntry).delete()
        session.commit()
        session.close()
        
    # Drop the database tables
    Base.metadata.drop_all(engine)

    context.server_thread.join(timeout=1) 
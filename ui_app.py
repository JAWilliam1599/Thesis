"""
Backward compatibility wrapper for the refactored UI.

The actual UI code is now modularized in the ui/ package.
To run the app properly, use: streamlit run ui/main.py
"""

# Import and run the main application
from ui.main import main

if __name__ == "__main__":
    main()

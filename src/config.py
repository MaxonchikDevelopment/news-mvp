# Import the standard library 'os' to interact with environment variables
import os

# Import 'load_dotenv' from the 'python-dotenv' package,
# which allows loading environment variables from a local .env file
from dotenv import load_dotenv

# Load environment variables from the .env file into the system environment
load_dotenv()

# Fetch the MISTRAL_API_KEY from environment variables.
# If it's not found, use an empty string as a fallback.
MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")

# If the API key is missing, raise an error to prevent the app from running
# without the required authentication credentials.
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY is missing! Please add it to your .env file.")

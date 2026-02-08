import os
import requests # type: ignore[import]
from google.genai import types # type: ignore[import]

def search_web(query, count=5):
    """
    Wyszukuje informacje w internecie używając Brave Search API.
    Przydatne do zdobywania aktualnych informacji, dokumentacji lub rozwiązywania błędów.
    """
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return "Error: BRAVE_API_KEY not found in environment variables."

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }
    params = {
        "q": query,
        "count": min(count, 10)  # Limit max 10 wyników
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("web", {}).get("results", [])
            
            if not results:
                return "No results found."
            
            # Formatujemy wyniki w czytelną listę dla LLM
            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "No title")
                link = result.get("url", "No link")
                desc = result.get("description", "No description")
                formatted_results.append(f"{i}. [{title}]({link})\n   {desc}")
            
            return "\n\n".join(formatted_results)
        
        elif response.status_code == 429:
            return "Error: Rate limit exceeded for Brave Search API."
        elif response.status_code == 401:
            return "Error: Invalid Brave API Key."
        else:
            return f"Error: Brave API returned status code {response.status_code}"

    except Exception as e:
        return f"Error connecting to search API: {str(e)}"

# Definicja schematu dla Gemini
schema_search_web = types.FunctionDeclaration(
    name="search_web",
    description="Searches the internet for real-time information using Brave Search.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search query (e.g., 'python 3.12 release date', 'fix error X').",
            ),
            "count": types.Schema(
                type=types.Type.INTEGER,
                description="Number of results to return (default 5).",
            ),
        },
        required=["query"],
    ),
)
import os
import requests # type: ignore[import]

def search_web(query, count=5):
    """
    Searches the internet for information using the Brave Search API.
    Useful for getting up-to-date information, documentation, or solving errors.
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
        "count": min(count, 10)  # Limit to at most 10 results
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("web", {}).get("results", [])
            
            if not results:
                return "No results found."
            
            # Format the results into a readable list for the LLM
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


# Tool schema in OpenAI format (works with all providers; working_directory is injected automatically)
schema_search_web = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Searches the internet for real-time information using Brave Search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (e.g., 'python 3.12 release date', 'fix error X')."
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)."
                }
            },
            "required": [
                "query"
            ]
        }
    }
}

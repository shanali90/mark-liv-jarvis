import urllib.request
import urllib.parse
import json

def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city = parameters.get("city")
    if not city or not isinstance(city, str) or not city.strip():
        msg = "Sir, the city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    
    try:
        # 1. Geocode the city
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            geo_data = json.loads(resp.read().decode('utf-8'))
            
        if not geo_data.get("results"):
            return f"Could not find coordinates for city: {city}"
            
        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]
        resolved_name = geo_data["results"][0].get("name", city)
        country = geo_data["results"][0].get("country", "")
        
        # 2. Get Weather Data
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m&timezone=auto"
        req2 = urllib.request.Request(weather_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req2, timeout=15) as resp:
            weather_data = json.loads(resp.read().decode('utf-8'))
            
        cur = weather_data.get("current", {})
        temp = cur.get("temperature_2m", "N/A")
        feels_like = cur.get("apparent_temperature", "N/A")
        wind = cur.get("wind_speed_10m", "N/A")
        humidity = cur.get("relative_humidity_2m", "N/A")
        
        # Open-Meteo WMO Weather codes
        wmo_codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle", 
            55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            85: "Slight snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
            96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
        }
        condition = wmo_codes.get(cur.get("weather_code", 0), "Unknown")
        
        msg = f"Current weather in {resolved_name}, {country}: {condition}, {temp}°C (feels like {feels_like}°C) with {humidity}% humidity and wind speed of {wind} km/h."
        _log(msg, player)
        
        if session_memory:
            try:
                session_memory.set_last_search(query=city, response=msg)
            except Exception:
                pass
                
        return msg

    except Exception as e:
        msg = f"Sir, I couldn't fetch the weather from Open-Meteo: {e}"
        _log(msg, player)
        return msg

def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass

TOOL = {
    "name": "weather_report",
    "description": "Gives the weather report to user using Open-Meteo data",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "City name"
            }
        },
        "required": ["city"]
    },
    "handler": weather_action,
}

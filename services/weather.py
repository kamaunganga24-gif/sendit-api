import os
import httpx
from typing import Optional, Dict

WEATHER_API_URL = os.getenv("WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast")
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"

async def get_coordinates(city: str, country: str = "Kenya") -> Optional[tuple]:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                GEOCODING_API_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                return (result["latitude"], result["longitude"])
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None

async def get_weather(city: str, country: str = "Kenya") -> Optional[Dict]:
    coordinates = await get_coordinates(city, country)
    if not coordinates:
        return {"error": "Could not locate city coordinates"}
    
    lat, lon = coordinates
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                WEATHER_API_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": True,
                    "temperature_unit": "celsius",
                    "timezone": "Africa/Nairobi"
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            current = data.get("current_weather", {})
            return {
                "city": city,
                "country": country,
                "temperature": current.get("temperature"),
                "windspeed": current.get("windspeed"),
                "weathercode": current.get("weathercode"),
                "time": current.get("time"),
                "source": "Open-Meteo"
            }
        except Exception as e:
            print(f"Weather service failure: {e}")
            return {"error": str(e)}

async def dispatch_webhook_event(event_type: str, payload: dict, session):
    from sqlmodel import select
    from models.webhook import WebhookSubscription
    
    subs = session.exec(
        select(WebhookSubscription).where(
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.is_active == True
        )
    ).all()
    
    async with httpx.AsyncClient() as client:
        for sub in subs:
            try:
                await client.post(sub.url, json=payload, timeout=5.0)
            except Exception as e:
                print(f"Webhook delivery failed for {sub.url}: {e}")
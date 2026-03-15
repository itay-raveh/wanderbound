from pydantic import BaseModel


class WeatherData(BaseModel):
    temp: float
    feels_like: float
    icon: str


class Weather(BaseModel):
    day: WeatherData
    night: WeatherData | None = None

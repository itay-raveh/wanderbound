from __future__ import annotations

from pydantic import BaseModel

from psagen.models.trip import Step


class WeatherData(BaseModel):
    temp: float
    feels_like: float
    icon: str


class Weather(BaseModel):
    day: WeatherData
    night: WeatherData | None = None

    @classmethod
    def from_step(cls, step: Step) -> Weather:
        return Weather(
            day=WeatherData(
                temp=step.weather_temperature,
                feels_like=step.weather_temperature,
                icon=step.weather_condition,
            )
        )


class Flag(BaseModel):
    flag_url: str
    accent_color: str


class Map(BaseModel):
    svg_content: str
    dot_position: tuple[float, float]


class EnrichedStep(Step):
    altitude: float
    weather: Weather
    flag: Flag
    map: Map

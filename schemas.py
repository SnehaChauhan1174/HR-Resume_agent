from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional
import re

class Education(BaseModel):
    degree: str
    institute: str
    cgpa: Optional[float] = None
    year: Optional[int] = None

    @field_validator("cgpa")
    @classmethod
    def validate_cgpa(cls, v):
        if v is not None and not (0.0 <= v <= 10.0):
            raise ValueError(f"CGPA {v} is out of valid range (0-10)")
        return v

    @field_validator("year")
    @classmethod
    def validate_year(cls, v):
        if v is not None and not (1980 <= v <= 2030):
            raise ValueError(f"Year {v} seems invalid")
        return v


class Experience(BaseModel):
    role: str
    company: str
    duration_months: Optional[int] = None
    skills_used: list[str] = []

    @field_validator("duration_months")
    @classmethod
    def validate_duration(cls, v):
        if v is not None and v < 0:
            raise ValueError("duration_months cannot be negative")
        return v


class Project(BaseModel):
    name: str
    description: Optional[str] = None
    tech_stack: list[str] = []


class Resume(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    education: list[Education] = []
    experience: list[Experience] = []
    skills: list[str] = []
    total_experience_years: Optional[float] = None
    projects: list[Project] = []
    certifications: list[str] = []

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(pattern, v):
                raise ValueError(f"Invalid email format: {v}")
        return v

    @field_validator("total_experience_years")
    @classmethod
    def validate_experience(cls, v):
        if v is not None and v < 0:
            raise ValueError("total_experience_years cannot be negative")
        return v

    @model_validator(mode="after")
    def check_minimum_data(self):
        # Reject if resume has basically nothing useful
        if not self.name and not self.email and not self.skills:
            raise ValueError("Resume has no useful data — name, email, and skills all missing")
        return self


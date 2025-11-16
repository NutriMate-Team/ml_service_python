from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class UserProfile(BaseModel):
    weightKg: float
    heightCm: float
    age: int
    gender: str # "Nam" hoặc "Nữ"
    activityLevel: str # "SEDENTARY", "LIGHT", "MODERATE", "ACTIVE", "VERY_ACTIVE"

@app.post("/recommendations")
def get_recommendations(profile: UserProfile):


    # Tính BMR (Harris-Benedict Equation)
    if profile.gender == "Nam":
        bmr = 88.362 + (13.397 * profile.weightKg) + (4.799 * profile.heightCm) - (5.677 * profile.age)
    else: # "Nữ"
        bmr = 447.593 + (9.247 * profile.weightKg) + (3.098 * profile.heightCm) - (4.330 * profile.age)

    # Tính TDEE (BMR * Mức độ vận động)
    activity_multipliers = {
        "SEDENTARY": 1.2,
        "LIGHT": 1.375,
        "MODERATE": 1.55,
        "ACTIVE": 1.725,
        "VERY_ACTIVE": 1.9
    }

    multiplier = activity_multipliers.get(profile.activityLevel, 1.2) 
    tdee = bmr * multiplier # Lượng calo để duy trì cân nặng

    recommended_calories = tdee - 500

    return {
        "recommendedCalories": round(recommended_calories),
        "maintenanceCalories": round(tdee) # Calo duy trì
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
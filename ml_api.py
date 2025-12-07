from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI()

class UserProfile(BaseModel):
    weightKg: float
    heightCm: float
    age: int
    gender: str # "Nam" hoặc "Nữ"
    activityLevel: str # "SEDENTARY", "LIGHT", "MODERATE", "ACTIVE", "VERY_ACTIVE"
    targetWeightKg: Optional[float] = None # Optional: The weight the user wants to reach

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

    # DYNAMIC GOAL LOGIC: Tính Calo Mục tiêu dựa trên mục tiêu cân nặng
    if profile.targetWeightKg is not None:
        if profile.targetWeightKg > profile.weightKg:
            # Mục tiêu Tăng cân (Thặng dư 500 calo)
            recommended_calories = tdee + 500
        elif profile.targetWeightKg < profile.weightKg:
            # Mục tiêu Giảm cân (Thâm hụt 500 calo)
            recommended_calories = tdee - 500
        else:
            # Mục tiêu Duy trì hoặc không xác định (TDEE)
            recommended_calories = tdee
    else:
        # Nếu không có targetWeightKg, mặc định dùng deficit (giảm cân)
        recommended_calories = tdee - 500
    
    # [QUAN TRỌNG] Giới hạn an toàn: Không bao giờ để recommended_calories xuống dưới BMR
    # (mức tối thiểu để sống)
    if recommended_calories < bmr:
        recommended_calories = bmr

    return {
        "recommendedCalories": round(recommended_calories),
        "maintenanceCalories": round(tdee) # Calo duy trì
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
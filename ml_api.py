from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Tuple
from enum import Enum
import uvicorn

app = FastAPI(
    title="NutriMate ML Service",
    description="Health & Fitness Recommendation API",
    version="1.0.0"
)


# ==================== ENUMS ====================

class Gender(str, Enum):
    """Giới tính"""
    MALE = "Nam"
    FEMALE = "Nữ"


class ActivityLevel(str, Enum):
    """Mức độ vận động - tương thích với NestJS Prisma schema"""
    SEDENTARY = "SEDENTARY"      # Ít vận động
    LIGHT = "LIGHT"              # Vận động nhẹ
    MODERATE = "MODERATE"        # Vận động vừa
    ACTIVE = "ACTIVE"            # Năng động
    VERY_ACTIVE = "VERY_ACTIVE"  # Rất năng động


class Goal(str, Enum):
    """Mục tiêu cân nặng"""
    LOSE = "LOSE"        # Giảm cân
    GAIN = "GAIN"        # Tăng cân
    MAINTAIN = "MAINTAIN"  # Duy trì


# ==================== MODELS ====================

class UserProfile(BaseModel):
    """Thông tin hồ sơ người dùng"""
    weightKg: float = Field(..., gt=0, description="Cân nặng (kg)")
    heightCm: float = Field(..., gt=0, description="Chiều cao (cm)")
    age: int = Field(..., gt=0, le=150, description="Tuổi")
    gender: Gender = Field(..., description="Giới tính")
    activityLevel: ActivityLevel = Field(..., description="Mức độ vận động")
    targetWeightKg: Optional[float] = Field(None, gt=0, description="Cân nặng mục tiêu (kg)")
    goal: Optional[Goal] = Field(None, description="Mục tiêu (LOSE/GAIN/MAINTAIN)")

    @model_validator(mode='after')
    def validate_target_weight(self):
        """Validate targetWeightKg phải hợp lý so với weight hiện tại"""
        if self.targetWeightKg is not None:
            # Cho phép chênh lệch tối đa 100kg (để linh hoạt)
            if abs(self.targetWeightKg - self.weightKg) > 100:
                raise ValueError("Cân nặng mục tiêu không hợp lý so với cân nặng hiện tại")
        return self


class MacroBreakdown(BaseModel):
    """Phân bổ macro nutrients"""
    proteinGram: float = Field(..., description="Protein (gram)")
    fatGram: float = Field(..., description="Fat (gram)")
    carbGram: float = Field(..., description="Carbohydrate (gram)")
    proteinPerKg: float = Field(..., description="Protein theo g/kg cân nặng")


class RecommendationResponse(BaseModel):
    """Response từ API recommendations"""
    bmr: float = Field(..., description="Basal Metabolic Rate (calo)")
    tdee: float = Field(..., description="Total Daily Energy Expenditure (calo)")
    recommendedCalories: float = Field(..., description="Calo mục tiêu khuyến nghị")
    bmi: float = Field(..., description="Body Mass Index")
    macros: MacroBreakdown = Field(..., description="Phân bổ macro nutrients")
    note: str = Field(..., description="Nhận xét và chiến lược ăn uống")


# ==================== BUSINESS LOGIC ====================

def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: Gender) -> float:
    """
    Tính BMR (Basal Metabolic Rate) sử dụng Harris-Benedict Equation
    
    Args:
        weight_kg: Cân nặng (kg)
        height_cm: Chiều cao (cm)
        age: Tuổi
        gender: Giới tính
    
    Returns:
        BMR (calo/ngày)
    """
    if gender == Gender.MALE:
        bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
    else:  # Gender.FEMALE
        bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)
    
    return round(bmr, 2)


def calculate_tdee(bmr: float, activity_level: ActivityLevel) -> float:
    """
    Tính TDEE (Total Daily Energy Expenditure)
    
    Args:
        bmr: Basal Metabolic Rate
        activity_level: Mức độ vận động
    
    Returns:
        TDEE (calo/ngày)
    """
    activity_multipliers = {
        ActivityLevel.SEDENTARY: 1.2,
        ActivityLevel.LIGHT: 1.375,
        ActivityLevel.MODERATE: 1.55,
        ActivityLevel.ACTIVE: 1.725,
        ActivityLevel.VERY_ACTIVE: 1.9
    }
    
    multiplier = activity_multipliers.get(activity_level, 1.2)
    tdee = bmr * multiplier
    
    return round(tdee, 2)


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """
    Tính BMI (Body Mass Index)
    
    Args:
        weight_kg: Cân nặng (kg)
        height_cm: Chiều cao (cm)
    
    Returns:
        BMI
    """
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)
    return round(bmi, 2)


def determine_goal(profile: UserProfile) -> Goal:
    """
    Xác định mục tiêu dựa trên goal field hoặc targetWeightKg
    
    Args:
        profile: UserProfile
    
    Returns:
        Goal (LOSE/GAIN/MAINTAIN)
    """
    # Nếu có goal field, ưu tiên sử dụng
    if profile.goal is not None:
        return profile.goal
    
    # Nếu không có goal, suy luận từ targetWeightKg
    if profile.targetWeightKg is not None:
        diff = profile.targetWeightKg - profile.weightKg
        
        # Ngưỡng chênh lệch nhỏ (0.5kg) coi như duy trì
        if abs(diff) < 0.5:
            return Goal.MAINTAIN
        elif diff > 0:
            return Goal.GAIN
        else:
            return Goal.LOSE
    
    # Mặc định: Duy trì (KHÔNG mặc định giảm cân)
    return Goal.MAINTAIN


def calculate_target_calories(tdee: float, goal: Goal, bmr: float) -> float:
    """
    Tính calo mục tiêu dựa trên goal
    
    Args:
        tdee: Total Daily Energy Expenditure
        goal: Mục tiêu (LOSE/GAIN/MAINTAIN)
        bmr: Basal Metabolic Rate (để giới hạn tối thiểu)
    
    Returns:
        Calo mục tiêu (đã được validate)
    """
    if goal == Goal.LOSE:
        target_calories = tdee - 500
    elif goal == Goal.GAIN:
        target_calories = tdee + 500
    else:  # Goal.MAINTAIN
        target_calories = tdee
    
    # Giới hạn an toàn: không bao giờ dưới BMR
    if target_calories < bmr:
        target_calories = bmr
    
    # Giới hạn tối đa: 4500 calo
    if target_calories > 4500:
        target_calories = 4500
    
    return round(target_calories, 2)


def calculate_macros(
    target_calories: float,
    goal: Goal,
    activity_level: ActivityLevel,
    weight_kg: float
) -> Tuple[float, float, float]:
    """
    Tính macro percentages dựa trên goal và activity level
    
    Args:
        target_calories: Calo mục tiêu
        goal: Mục tiêu (LOSE/GAIN/MAINTAIN)
        activity_level: Mức độ vận động
        weight_kg: Cân nặng (để tính protein per kg)
    
    Returns:
        Tuple (protein_percent, fat_percent, carb_percent)
    """
    is_high_activity = activity_level in [ActivityLevel.ACTIVE, ActivityLevel.VERY_ACTIVE]
    
    if goal == Goal.GAIN:
        if is_high_activity:
            # Tăng cân + Vận động mạnh: Protein cao, Fat đủ, Carbs cao để phục hồi
            protein_percent = 0.35
            fat_percent = 0.25
            carb_percent = 0.40
        else:
            # Tăng cân + Vận động nhẹ/vừa
            protein_percent = 0.30
            fat_percent = 0.30
            carb_percent = 0.40
    elif goal == Goal.LOSE:
        if is_high_activity:
            # Giảm cân + Vận động mạnh: Protein cao để giữ cơ
            protein_percent = 0.40
            fat_percent = 0.25
            carb_percent = 0.35
        else:
            # Giảm cân + Vận động nhẹ/vừa
            protein_percent = 0.35
            fat_percent = 0.30
            carb_percent = 0.35
    else:  # Goal.MAINTAIN
        if is_high_activity:
            # Duy trì + Vận động mạnh: Carbs cao để phục hồi
            protein_percent = 0.30
            fat_percent = 0.25
            carb_percent = 0.45
        else:
            # Duy trì + Vận động nhẹ/vừa
            protein_percent = 0.30
            fat_percent = 0.30
            carb_percent = 0.40
    
    # Đảm bảo tổng = 100%
    total = protein_percent + fat_percent + carb_percent
    if abs(total - 1.0) > 0.01:  # Cho phép sai số nhỏ do làm tròn
        # Normalize nếu cần
        protein_percent /= total
        fat_percent /= total
        carb_percent /= total
    
    return protein_percent, fat_percent, carb_percent


def generate_nutrition_note(goal: Goal, activity_level: ActivityLevel, bmi: float) -> str:
    """
    Tạo nhận xét và chiến lược ăn uống phù hợp
    
    Args:
        goal: Mục tiêu
        activity_level: Mức độ vận động
        bmi: Body Mass Index
    
    Returns:
        Nhận xét (string)
    """
    activity_text = {
        ActivityLevel.SEDENTARY: "ít vận động",
        ActivityLevel.LIGHT: "vận động nhẹ",
        ActivityLevel.MODERATE: "vận động vừa",
        ActivityLevel.ACTIVE: "năng động",
        ActivityLevel.VERY_ACTIVE: "rất năng động"
    }.get(activity_level, "vận động")
    
    bmi_status = ""
    if bmi < 18.5:
        bmi_status = "Bạn đang thiếu cân. "
    elif bmi > 25:
        bmi_status = "Bạn đang thừa cân. "
    
    if goal == Goal.GAIN:
        note = (
            f"{bmi_status}Mục tiêu của bạn là tăng cân với mức độ {activity_text}. "
            f"Tập trung vào protein chất lượng cao (thịt, cá, trứng, đậu) để xây dựng cơ bắp, "
            f"kết hợp carbs phức tạp (gạo lứt, yến mạch) để cung cấp năng lượng. "
            f"Nếu bạn tập luyện sức mạnh, hãy ăn bữa phụ sau tập để phục hồi tốt hơn."
        )
    elif goal == Goal.LOSE:
        note = (
            f"{bmi_status}Mục tiêu của bạn là giảm cân với mức độ {activity_text}. "
            f"Ưu tiên protein cao để giữ cơ bắp trong quá trình giảm cân, "
            f"giảm carbs tinh chế và tăng chất xơ. "
            f"Kết hợp cardio và tập sức mạnh để đốt mỡ hiệu quả. "
            f"Nhớ uống đủ nước và ngủ đủ giấc."
        )
    else:  # Goal.MAINTAIN
        note = (
            f"{bmi_status}Mục tiêu của bạn là duy trì cân nặng với mức độ {activity_text}. "
            f"Duy trì chế độ ăn cân bằng với đủ protein, chất béo lành mạnh và carbs. "
            f"Nếu bạn vận động nhiều, tăng carbs để phục hồi. "
            f"Theo dõi cân nặng hàng tuần để điều chỉnh kịp thời."
        )
    
    return note


# ==================== API ENDPOINT ====================

@app.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(profile: UserProfile) -> RecommendationResponse:
    """
    Tính toán khuyến nghị dinh dưỡng dựa trên hồ sơ người dùng
    
    - Tính BMR, TDEE, BMI
    - Xác định mục tiêu (LOSE/GAIN/MAINTAIN)
    - Tính calo mục tiêu và phân bổ macro
    - Trả về nhận xét và chiến lược ăn uống
    """
    try:
        # 1. Tính BMR
        bmr = calculate_bmr(profile.weightKg, profile.heightCm, profile.age, profile.gender)
        
        # 2. Tính TDEE
        tdee = calculate_tdee(bmr, profile.activityLevel)
        
        # 3. Tính BMI
        bmi = calculate_bmi(profile.weightKg, profile.heightCm)
        
        # 4. Xác định mục tiêu
        goal = determine_goal(profile)
        
        # 5. Tính calo mục tiêu
        target_calories = calculate_target_calories(tdee, goal, bmr)
        
        # 6. Tính macro percentages
        protein_percent, fat_percent, carb_percent = calculate_macros(
            target_calories, goal, profile.activityLevel, profile.weightKg
        )
        
        # 7. Tính macro grams
        # Protein: 4 cal/g, Fat: 9 cal/g, Carbs: 4 cal/g
        protein_gram = round((target_calories * protein_percent) / 4, 1)
        fat_gram = round((target_calories * fat_percent) / 9, 1)
        carb_gram = round((target_calories * carb_percent) / 4, 1)
        
        # 8. Tính protein per kg
        protein_per_kg = round(protein_gram / profile.weightKg, 2)
        
        # 9. Tạo nhận xét
        note = generate_nutrition_note(goal, profile.activityLevel, bmi)
        
        # 10. Trả về response
        return RecommendationResponse(
            bmr=bmr,
            tdee=tdee,
            recommendedCalories=target_calories,
            bmi=bmi,
            macros=MacroBreakdown(
                proteinGram=protein_gram,
                fatGram=fat_gram,
                carbGram=carb_gram,
                proteinPerKg=protein_per_kg
            ),
            note=note
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "NutriMate ML Service"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

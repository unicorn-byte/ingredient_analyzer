def analyze_ingredients(ingredients):
    rules = {
        "sugar": ("High sugar intake increases diabetes risk", 30),
        "salt": ("Excess salt may increase blood pressure", 20),
        "palm oil": ("High saturated fat content", 15),
        "msg": ("May cause headaches in sensitive people", 10),
    }

    score = 100
    harmful = []

    for ing in ingredients:
        for key, (reason, penalty) in rules.items():
            if key in ing.lower():
                score -= penalty
                harmful.append({
                    "name": ing,
                    "reason": reason,
                    "health_impact": reason
                })

    score = max(score, 0)

    if score >= 70:
        light, assess = "GREEN", "Generally safe"
    elif score >= 40:
        light, assess = "YELLOW", "Consume in moderation"
    else:
        light, assess = "RED", "Not recommended frequently"

    return {
        "safety_score": score,
        "traffic_light": light,
        "overall_assessment": assess,
        "harmful_ingredients": harmful,
        "recommendations": [
            "Limit consumption" if light != "GREEN" else "No major concerns"
        ]
    }

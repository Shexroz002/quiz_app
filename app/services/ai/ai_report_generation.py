from typing import List, Dict, Any


def format_percentage(value: float) -> str:
    return f"{value:.1f}%" if value % 1 else f"{int(value)}%"


def report_generation(stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Report generation rules:

    1. Kuchli tomon:
       - faqat percentage >= 60 bo'lsa kuchli tomon deb aytiladi
       - bunda correct_answer ham 0 dan katta bo'lishi kerak
       - bir nechta bo'lishi mumkin
       - agar bir nechta bo'lsa, text ichida hammasi chiqariladi

    2. Fokus berilgan fan:
       - eng ko'p total_answer bo'lgan fan
       - bu kuchli tomon o'rnida emas, faqat harakat/faollik sifatida ishlatiladi

    3. Yaxshilash kerak:
       - percentage eng past bo'lgan fan olinadi
       - lekin matn kamsituvchi bo'lmasligi kerak

    4. Keyingi maqsad:
       - eng past natijali fanga kichik real maqsad beriladi
    """

    base_response = {
        "title": "AI Tavsiyasi",
        "badge": "Yangi",
        "subtitle": "Sun'iy intellekt tahlili",
    }

    if not stats:
        return {
            **base_response,
            "strong_sides": {
                "title": "Kuchli tomonlaringiz",
                "icon": "🎯",
                "text": "Hozircha tahlil uchun yetarli ma’lumot yo‘q. Bir nechta test ishlaganingizdan so‘ng sizga aniqroq tavsiyalar berish mumkin bo‘ladi."
            },
            "improvement": {
                "title": "Yaxshilash kerak",
                "icon": "⚠️",
                "text": "Tavsiyalar shakllanishi uchun kamida bir nechta fan bo‘yicha test ishlash tavsiya etiladi."
            },
            "next_goal": {
                "title": "Keyingi maqsad",
                "icon": "📈",
                "text": "Boshlash uchun 5–10 ta test ishlab, dastlabki natijalarni shakllantirib oling."
            }
        }

    # Kuchli tomon uchun nomzodlar: faqat 60%+
    strong_candidates = [
        item for item in stats
        if item.get("percentage", 0) >= 60 and item.get("correct_answer", 0) > 0
    ]

    # Percentage past fan
    weakest_subject = min(
        stats,
        key=lambda x: (x.get("percentage", 0), x.get("correct_answer", 0))
    )

    # Eng ko‘p ishlangan fan = fokus berilgan fan
    focused_subject = max(
        stats,
        key=lambda x: (x.get("total_answer", 0), x.get("correct_answer", 0))
    )

    # 1. Kuchli tomon matni
    if strong_candidates:
        strong_candidates = sorted(
            strong_candidates,
            key=lambda x: (
                x.get("percentage", 0),
                x.get("correct_answer", 0),
                x.get("total_answer", 0)
            ),
            reverse=True
        )

        if len(strong_candidates) == 1:
            best_strong = strong_candidates[0]
            strong_text = (
                f"{best_strong['subject_name']} fanida yaxshi natija ko‘rsatgansiz: "
                f"{format_percentage(best_strong['percentage'])}. "
                f"Bu fandan {best_strong['correct_answer']} ta to‘g‘ri javob bergansiz. "
                f"Shu tempni davom ettirsangiz, natijangiz yanada mustahkamlanadi."
            )
        else:
            subject_parts = [
                f"{item['subject_name']} ({format_percentage(item['percentage'])})"
                for item in strong_candidates
            ]

            strong_text = (
                f"Siz {', '.join(subject_parts)} fanlarida yaxshi natija ko‘rsatgansiz. "
                "Bu fanlarda bilimlaringiz barqaror shakllanayotganini ko‘rsatadi. "
                "Shu tempni davom ettirsangiz, natijalaringiz yanada mustahkamlanadi."
            )
    else:
        strong_text = (
            f"Siz hozircha eng ko‘p e’tiborni {focused_subject['subject_name']} faniga qaratgansiz "
            f"va bu fandan {focused_subject['total_answer']} ta savol ishlagansiz. "
            f"Bu yaxshi odat — muntazam mashq natijani asta-sekin yaxshilab boradi."
        )

    # 2. Yaxshilash kerak matni
    weak_percentage = weakest_subject.get("percentage", 0)
    weak_name = weakest_subject["subject_name"]

    if weak_percentage < 20:
        improvement_text = (
            f"{weak_name} fanida hozircha ko‘proq mashq qilish kerak bo‘ladi. "
            f"Hozirgi natija {format_percentage(weak_percentage)}. "
            f"Mavzularni kichik bo‘limlarga ajratib, har kuni 15–20 daqiqa ishlash yaxshi samara beradi."
        )
    elif weak_percentage < 40:
        improvement_text = (
            f"{weak_name} fanida natijani yaxshilash uchun imkoniyat bor. "
            f"Hozirgi ko‘rsatkich {format_percentage(weak_percentage)}. "
            f"Muntazam mashq va xatolar ustida ishlash bu fandagi o‘sishni tezlashtiradi."
        )
    else:
        improvement_text = (
            f"{weak_name} fanida natijani yanada barqaror qilish mumkin. "
            f"Hozirgi ko‘rsatkich {format_percentage(weak_percentage)}. "
            f"Bir nechta qo‘shimcha mashq bilan bu natijani oshirish mumkin."
        )

    # 3. Keyingi maqsad
    current_correct = weakest_subject.get("correct_answer", 0)
    current_total = weakest_subject.get("total_answer", 0)
    extra_tests = 5

    estimated_extra_correct = max(2, min(4, extra_tests))
    projected_total = current_total + extra_tests
    projected_correct = current_correct + estimated_extra_correct
    projected_percentage = round((projected_correct / projected_total) * 100, 1) if projected_total else 0

    next_goal_text = (
        f"{weak_name} fanidan yana {extra_tests} ta test ishlab ko‘rsangiz, "
        f"natijangizni taxminan {format_percentage(projected_percentage)} gacha olib chiqish imkoniyati bor. "
        f"Kichik va muntazam qadamlar eng yaxshi natijani beradi."
    )

    return {
        **base_response,
        "strong_sides": {
            "title": "Kuchli tomonlaringiz",
            "icon": "🎯",
            "text": strong_text
        },
        "improvement": {
            "title": "Yaxshilash kerak",
            "icon": "⚠️",
            "text": improvement_text
        },
        "next_goal": {
            "title": "Keyingi maqsad",
            "icon": "📈",
            "text": next_goal_text
        }
    }
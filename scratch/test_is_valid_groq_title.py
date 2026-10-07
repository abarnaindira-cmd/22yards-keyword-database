import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scratch.run_safe_groq_batch_runner import is_valid_groq_title

def run_unit_tests():
    print("=== TESTING is_valid_groq_title() LOGIC ===")

    test_cases = [
        # (title, product_name, expected_result, description)
        (
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Exact match (same case): title == product_name"
        ),
        (
            "Striker Popular Willow Cricket Tennis Bat",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Normalized match (title-case vs UPPER): title == product_name"
        ),
        (
            " Striker Popular Willow Cricket Tennis Bat ",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT\n",
            False,
            "Whitespace-padded match: title == product_name"
        ),
        (
            "Striker Popular Willow Tennis Bat - Premium English Willow Cricket Bat",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            True,
            "Different generated wording (Valid Groq Title)"
        ),
        (
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT | cricket bat, tennis bat",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Title containing '|' (Legacy Fallback)"
        ),
        (
            "MANUAL_REVIEW_REQUIRED",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Title == 'MANUAL_REVIEW_REQUIRED'"
        ),
        (
            "",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Empty title"
        ),
        (
            "   ",
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "Whitespace-only title"
        ),
        (
            None,
            "STRIKER POPULAR WILLOW CRICKET TENNIS BAT",
            False,
            "None title"
        )
    ]

    all_passed = True
    for idx, (title, prod_name, expected, desc) in enumerate(test_cases, 1):
        res = is_valid_groq_title(title, prod_name)
        status = "PASSED" if res == expected else "FAILED"
        if res != expected:
            all_passed = False
        print(f"Test {idx:2d} [{status}]: {desc}")
        print(f"         title       : {repr(title)}")
        print(f"         product_name: {repr(prod_name)}")
        print(f"         Expected    : {expected} | Actual: {res}")
        print("-" * 65)

    if all_passed:
        print("\nALL UNIT TESTS PASSED PERFECTLY!")
    else:
        print("\nSOME TESTS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    run_unit_tests()

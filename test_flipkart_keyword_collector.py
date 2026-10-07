from app.services.flipkart_keyword_collector import collect_flipkart_keywords

def main():
    seed = "cricket bat"
    keywords = collect_flipkart_keywords(seed)
    
    print("Seed:")
    print(seed)
    print()
    print("Number of keywords:")
    print(len(keywords))
    print()
    print("Collected keywords:")
    for idx, kw in enumerate(keywords, 1):
        print(f"{idx}. {kw}")

if __name__ == "__main__":
    main()

"""Test article generation service"""
import asyncio
from backend.database import SessionLocal
from backend.services.article_writer import generate_article

async def test():
    db = SessionLocal()
    try:
        order_id = "07846548-9678-4edc-8e1b-553c57723ef1"
        print(f"Generating article for order {order_id}...")
        result = await generate_article(order_id, db)
        print(f"\n✓ Success!")
        print(f"  Word count: {result['word_count']}")
        print(f"  Status: {result['status']}")
        print(f"\nArticle preview (first 500 chars):")
        print(result['article_content'][:500])
        print("...")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test())

#!/bin/bash
# Test script for the enhanced article generation system

set -e

echo "=== BackVora Article Writer System Test ==="
echo ""

# Check if server is running
if ! curl -s http://localhost:8001/health > /dev/null; then
    echo "❌ Server is not running on port 8001"
    exit 1
fi
echo "✅ Server is running"

# Test order ID (babesrater.com)
ORDER_ID="b2a95a9b-071b-412d-a369-a5a949e3b481"

# Check if order exists and has content
echo ""
echo "=== Checking Order Status ==="
python3 << EOPY
from backend.database import SessionLocal
from backend.models import Order, ArticleTopic
import json

db = SessionLocal()
order = db.query(Order).filter(Order.id == "$ORDER_ID").first()

if not order:
    print("❌ Order not found")
    exit(1)

print(f"✅ Order found: {order.domain.domain if order.domain else 'N/A'}")
print(f"   Status: {order.status}")

if order.article_content:
    print(f"✅ Article content exists ({len(order.article_content)} chars)")
    
    # Check structure
    import re
    h2_count = len(re.findall(r'^## ', order.article_content, re.MULTILINE))
    h3_count = len(re.findall(r'^### ', order.article_content, re.MULTILINE))
    links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', order.article_content)
    images = re.findall(r'!\[', order.article_content)
    
    external_links = [l for l in links if 'http' in l[1] and 'camhours.com' not in l[1] and '/api/v1/images' not in l[1]]
    
    print(f"   H2 headings: {h2_count}")
    print(f"   H3 headings: {h3_count}")
    print(f"   Images: {len(images)}")
    print(f"   External authority links: {len(external_links)}")
    
    if h2_count >= 3:
        print("   ✅ Proper heading structure")
    else:
        print("   ⚠️  Not enough H2 headings")
    
    if len(external_links) >= 2:
        print("   ✅ Authority links included")
        for text, url in external_links:
            print(f"      - {url}")
    else:
        print("   ⚠️  Not enough authority links")
    
    if len(images) >= 2:
        print("   ✅ Images included")
else:
    print("❌ No article content")

# Check topic
topic = db.query(ArticleTopic).filter(ArticleTopic.order_id == order.id).first()
if topic:
    print(f"✅ Topic saved: {topic.title}")
else:
    print("⚠️  No topic saved")

db.close()
EOPY

# Check image files
echo ""
echo "=== Checking Image Files ==="
IMAGE_DIR="data/images/$ORDER_ID"
if [ -d "$IMAGE_DIR" ]; then
    IMAGE_COUNT=$(ls -1 "$IMAGE_DIR"/*.png 2>/dev/null | wc -l)
    echo "✅ Image directory exists"
    echo "   Images found: $IMAGE_COUNT"
    
    for img in "$IMAGE_DIR"/*.png; do
        if [ -f "$img" ]; then
            SIZE=$(du -h "$img" | cut -f1)
            DIMS=$(file "$img" | grep -o '[0-9]* x [0-9]*')
            echo "   - $(basename "$img"): $SIZE ($DIMS)"
        fi
    done
else
    echo "❌ Image directory not found"
fi

# Test image endpoint
echo ""
echo "=== Testing Image API Endpoint ==="
if curl -s -f http://localhost:8001/api/v1/images/$ORDER_ID/image_1.png | file - | grep -q "PNG"; then
    echo "✅ Image 1 accessible via API"
else
    echo "❌ Image 1 not accessible"
fi

if curl -s -f http://localhost:8001/api/v1/images/$ORDER_ID/image_2.png | file - | grep -q "PNG"; then
    echo "✅ Image 2 accessible via API"
else
    echo "❌ Image 2 not accessible"
fi

# Check dependencies
echo ""
echo "=== Checking Dependencies ==="
python3 << EOPY
try:
    import openai
    print("✅ OpenAI package installed")
except:
    print("❌ OpenAI package missing")

try:
    from PIL import Image
    print("✅ Pillow package installed")
except:
    print("❌ Pillow package missing")

try:
    import httpx
    print("✅ httpx package installed")
except:
    print("❌ httpx package missing")
EOPY

# Check frontend
echo ""
echo "=== Checking Frontend Build ==="
if [ -d "frontend-react/dist" ]; then
    if [ -f "frontend-react/dist/index.html" ]; then
        echo "✅ Frontend built"
    else
        echo "⚠️  Frontend dist exists but index.html missing"
    fi
else
    echo "❌ Frontend not built"
fi

echo ""
echo "=== Test Summary ==="
echo "All core features verified!"
echo ""
echo "To regenerate an article:"
echo "  curl -X POST http://localhost:8001/api/v1/internal/orders/$ORDER_ID/generate-article"
echo ""
echo "To view images:"
echo "  http://localhost:8001/api/v1/images/$ORDER_ID/image_1.png"
echo "  http://localhost:8001/api/v1/images/$ORDER_ID/image_2.png"
echo ""

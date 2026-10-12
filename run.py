import os
from app import create_app
from app.config import Config

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "t")

    print("\n" + "=" * 70)
    print("  SMART CAMPUS 360 - INITIALIZING INTEGRATED PLATFORM")
    print(f"  Institution: {Config.COLLEGE_NAME}")
    print(f"  Location:    {Config.COLLEGE_LOCATION}")
    print("=" * 70)
    print("  [✓] Module 1: Smart Campus Navigation (A*/Dijkstra & Street View)")
    print("  [✓] Module 2: AI Lost & Found (OpenCV Visual Similarity)")
    print("  [✓] Module 3: Smart Canteen (Teacher-First Priority & QR Codes)")
    print(f"  [✓] Server Running at: http://{host}:{port}/")
    print("=" * 70 + "\n")

    app.run(host=host, port=port, debug=debug)

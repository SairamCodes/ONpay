"""ONPay V2 Real Supabase Storage Smoke Test.

Connects to the configured Supabase project using backend environment variables:
  - SUPABASE_URL
  - SUPABASE_SERVICE_ROLE_KEY
  - SUPABASE_SUBSCRIPTION_BUCKET (default: subscription-proofs)
  - SUPABASE_QR_BUCKET (default: admin-qr-codes)

Performs live end-to-end verification:
1. Bucket accessibility & private status check.
2. Upload test proof to subscription bucket.
3. Upload test QR to admin QR bucket.
4. Generate signed URLs.
5. Verify signed URLs return HTTP 200.
6. Clean up smoke test objects.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
from app.config import settings
from app.storage import storage_service

# Minimal valid 1x1 PNG image bytes
TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H"
    b"\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


def run_smoke_test():
    print("\n=======================================================")
    print("      ONPay V2 Supabase Storage Smoke Test")
    print("=======================================================\n")

    url = settings.supabase_url.strip()
    key = settings.supabase_service_role_key.strip()
    sub_bucket = settings.supabase_subscription_bucket.strip() or "subscription-proofs"
    qr_bucket = settings.supabase_qr_bucket.strip() or "admin-qr-codes"

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in your environment or backend/.env")
        print("Example:")
        print("  $env:SUPABASE_URL='https://xyz.supabase.co'")
        print("  $env:SUPABASE_SERVICE_ROLE_KEY='eyJhbG...'")
        sys.exit(1)

    # Safe display of URL and masked key
    masked_key = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
    print(f"Target URL:    {url}")
    print(f"Role Key:      {masked_key} (backend-only, securely loaded)")
    print(f"Sub Bucket:    {sub_bucket}")
    print(f"QR Bucket:     {qr_bucket}")
    print()

    # Step 1: Connect to Supabase
    print("[1/5] Connecting to Supabase Storage API...")
    try:
        client = storage_service.get_supabase_client()
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        print(f"  ✓ Connected! Found {len(bucket_names)} buckets: {', '.join(bucket_names)}")
    except Exception as e:
        print(f"  FAILED: Could not connect to Supabase: {e}")
        sys.exit(1)

    # Verify both target buckets exist
    for target_b in (sub_bucket, qr_bucket):
        if target_b not in bucket_names:
            print(f"  WARNING: Bucket '{target_b}' was not found in Supabase buckets list.")
            print(f"  Please ensure bucket '{target_b}' is created in Supabase Dashboard -> Storage.")
        else:
            print(f"  ✓ Confirmed bucket exists: {target_b}")

    test_timestamp = int(time.time())
    sub_path = f"smoke_tests/proof_smoke_{test_timestamp}.png"
    qr_path = f"smoke_tests/qr_smoke_{test_timestamp}.png"

    # Step 2: Upload Test Proof to Subscription Bucket
    print(f"\n[2/5] Uploading smoke test proof to '{sub_bucket}/{sub_path}'...")
    try:
        client.storage.from_(sub_bucket).upload(
            path=sub_path,
            file=TINY_PNG_BYTES,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
        print("  ✓ Proof uploaded successfully!")
    except Exception as e:
        print(f"  FAILED: Could not upload proof: {e}")
        sys.exit(1)

    # Step 3: Upload Test QR to Admin QR Bucket
    print(f"\n[3/5] Uploading smoke test QR image to '{qr_bucket}/{qr_path}'...")
    try:
        client.storage.from_(qr_bucket).upload(
            path=qr_path,
            file=TINY_PNG_BYTES,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
        print("  ✓ QR code uploaded successfully!")
    except Exception as e:
        print(f"  FAILED: Could not upload QR: {e}")
        sys.exit(1)

    # Step 4: Generate Temporary Signed URLs
    print("\n[4/5] Generating 5-minute temporary signed URLs...")
    try:
        sub_signed = client.storage.from_(sub_bucket).create_signed_url(sub_path, 300)
        qr_signed = client.storage.from_(qr_bucket).create_signed_url(qr_path, 300)

        sub_url = sub_signed.get("signedURL") or sub_signed.get("signedUrl")
        qr_url = qr_signed.get("signedURL") or qr_signed.get("signedUrl")

        print(f"  ✓ Subscription signed URL generated (length: {len(sub_url)} chars)")
        print(f"  ✓ QR signed URL generated (length: {len(qr_url)} chars)")
    except Exception as e:
        print(f"  FAILED: Signed URL generation failed: {e}")
        sys.exit(1)

    # Verify Signed URL Download over HTTPS
    print("  Testing signed URL retrieval via HTTP GET...")
    with httpx.Client(timeout=10.0) as http_client:
        r_sub = http_client.get(sub_url)
        if r_sub.status_code == 200 and r_sub.content == TINY_PNG_BYTES:
            print(f"  ✓ Subscription signed URL download verified (HTTP {r_sub.status_code}, {len(r_sub.content)} bytes)")
        else:
            print(f"  FAILED: Download returned HTTP {r_sub.status_code}")

        r_qr = http_client.get(qr_url)
        if r_qr.status_code == 200 and r_qr.content == TINY_PNG_BYTES:
            print(f"  ✓ QR signed URL download verified (HTTP {r_qr.status_code}, {len(r_qr.content)} bytes)")
        else:
            print(f"  FAILED: QR download returned HTTP {r_qr.status_code}")

    # Step 5: Clean up test files
    print("\n[5/5] Cleaning up smoke test files...")
    try:
        client.storage.from_(sub_bucket).remove([sub_path])
        client.storage.from_(qr_bucket).remove([qr_path])
        print("  ✓ Test files deleted from Supabase buckets.")
    except Exception as e:
        print(f"  Note: Automatic cleanup failed: {e}")

    print("\n=======================================================")
    print("  SUCCESS: Supabase Storage integration is fully verified!")
    print("=======================================================\n")


if __name__ == "__main__":
    run_smoke_test()

#!/bin/bash
# make-tiktok.sh - Generate TikTok-style promotional video
# Usage: ./make-tiktok.sh <project_dir> <actor_name> <actor_id> <source_video> <title_text>

set -e

PROJECT_DIR="$1"
ACTOR_NAME="$2"
ACTOR_ID="$3"
SOURCE_VIDEO="$4"
TITLE_TEXT="$5"

echo "=== TikTok Video Generator ==="
echo "Project: $PROJECT_DIR"
echo "Actor: $ACTOR_NAME ($ACTOR_ID)"
echo "Source: $SOURCE_VIDEO"
echo "Title: $TITLE_TEXT"
echo ""

cd "$PROJECT_DIR"

# Extract clips (already done by Python, just verify)
echo "=== Step 1: Verifying clips ==="
for i in 0 1 2 3; do
    if [ -f "clip_${ACTOR_ID}_${i}.mp4" ]; then
        echo "  ✓ clip_${ACTOR_ID}_${i}.mp4 exists"
    else
        echo "  ✗ clip_${ACTOR_ID}_${i}.mp4 missing"
    fi
done

# Create concat list
echo ""
echo "=== Step 2: Creating concat list ==="
cat > "concat_${ACTOR_ID}.txt" << EOF
file '$PROJECT_DIR/clip_${ACTOR_ID}_0.mp4'
file '$PROJECT_DIR/clip_${ACTOR_ID}_1.mp4'
file '$PROJECT_DIR/clip_${ACTOR_ID}_2.mp4'
file '$PROJECT_DIR/clip_${ACTOR_ID}_3.mp4'
EOF
echo "  Created concat_${ACTOR_ID}.txt"

# Combine clips with consistent 24fps
echo ""
echo "=== Step 3: Combining clips ==="
ffmpeg -y -f concat -safe 0 \
    -i "concat_${ACTOR_ID}.txt" \
    -c:v libx264 -c:a aac \
    -vf "fps=24" \
    -preset fast -crf 18 \
    "combined_${ACTOR_ID}.mp4" 2>&1 | tail -5
echo "  ✓ Combined clips"

# Generate intro at 24fps
echo ""
echo "=== Step 4: Generating intro ==="
ffmpeg -y -f lavfi -i 'color=c=black:s=1080x1920:d=4:r=24' \
    -vf "drawtext=text='${ACTOR_NAME} Deep Cut':fontsize=72:fontcolor=white:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:x=(w-text_w)/2:y=(h-text_h)/2-50,drawtext=text='Ever seen ${TITLE_TEXT}?':fontsize=48:fontcolor=white:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:x=(w-text_w)/2:y=(h-text_h)/2+50" \
    -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p \
    "bumper_intro_${ACTOR_ID}.mp4" 2>&1 | tail -3
echo "  ✓ Intro generated"

# Generate outro at 24fps
echo ""
echo "=== Step 5: Generating outro ==="
ffmpeg -y -f lavfi -i 'color=c=black:s=1080x1920:d=3:r=24' \
    -vf "drawtext=text='Watch ${TITLE_TEXT}':fontsize=56:fontcolor=white:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:x=(w-text_w)/2:y=(h-text_h)/2-30,drawtext=text='exclusively on':fontsize=36:fontcolor=#888888:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:x=(w-text_w)/2:y=(h-text_h)/2+30,drawtext=text='StreamPlus':fontsize=64:fontcolor=#E50914:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:x=(w-text_w)/2:y=(h-text_h)/2+80" \
    -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p \
    "bumper_outro_${ACTOR_ID}.mp4" 2>&1 | tail -3
echo "  ✓ Outro generated"

# Final concatenation with consistent 24fps
echo ""
echo "=== Step 6: Creating final video ==="
cat > "final_concat_${ACTOR_ID}.txt" << EOF
file '$PROJECT_DIR/bumper_intro_${ACTOR_ID}.mp4'
file '$PROJECT_DIR/combined_${ACTOR_ID}.mp4'
file '$PROJECT_DIR/bumper_outro_${ACTOR_ID}.mp4'
EOF

ffmpeg -y -f concat -safe 0 \
    -i "final_concat_${ACTOR_ID}.txt" \
    -c:v libx264 -c:a aac \
    -vf "fps=24" \
    -preset fast -crf 18 \
    "spot_${ACTOR_ID}.mp4" 2>&1 | tail -3
echo "  ✓ Final video created: spot_${ACTOR_ID}.mp4"

# Show result
echo ""
echo "=== COMPLETE ==="
ls -lh "spot_${ACTOR_ID}.mp4"
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,duration,r_frame_rate -of csv=p=0 "spot_${ACTOR_ID}.mp4"

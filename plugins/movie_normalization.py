import os
import subprocess
import re

# Configuration: Set path to your ffmpeg binary here
# If added to system PATH, just "ffmpeg" works.
# Otherwise, use full path: r"C:\Tools\ffmpeg\bin\ffmpeg.exe"
FFMPEG_BINARY = "ffmpeg"

def process(file_path):
    """
    Upmixes audio to 5.1 surround sound (Dual Audio: Normalized & Direct) using FFmpeg.
    """
    print(f"🔌 [Plugin] Upmixing audio for: {os.path.basename(file_path)}")
    
    # 1. Check if file exists and if FFmpeg is available
    if not os.path.exists(file_path):
        return file_path

    # 1.2 Check if TV Series (Skip)
    if re.search(r'S\d+E\d+', os.path.basename(file_path), re.IGNORECASE):
        print("   📺 TV Series detected. Skipping movie plugin.")
        return file_path

    # 1.5 Check if audio is already 5.1
    is_51 = False
    try:
        # Run ffmpeg to inspect file (stderr contains stream info)
        result = subprocess.run([FFMPEG_BINARY, "-i", file_path], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        # Look for "Stream #0:x... Audio: ... 5.1" or "6 channels"
        if re.search(r"Stream #0:\d+.*Audio:.*(5\.1|6 channels)", result.stderr):
            is_51 = True
            print("   ℹ️  Detected 5.1 Audio. Skipping upmix step.")
    except:
        pass

    # 2. Generate output filename
    # Example: "Movie.mkv" -> "Movie_DualAudio.mkv"
    base_name, extension = os.path.splitext(file_path)
    output_path = f"{base_name}_DualAudio{extension}"
    
    # Determine filter chain
    if is_51:
        # Already 5.1: Just split and normalize
        filter_complex = "[0:a]asplit=2[v1][v2];[v1]dynaudnorm=f=200:g=7[norm];[v2]anull[direct]"
    else:
        # Stereo: Upmix -> Split -> Normalize
        filter_complex = "[0:a]pan=5.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.5*c0+0.5*c1|BL=c0|BR=c1,asplit=2[v1][v2];[v1]dynaudnorm=f=200:g=7[norm];[v2]anull[direct]"

    # 3. Construct FFmpeg command
    cmd = [
        FFMPEG_BINARY, "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-i", file_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[norm]",
        "-map", "[direct]",
        "-map", "0:s?",
        "-c:v", "copy",
        "-c:a", "aac",
        "-ar", "48000",
        "-b:a", "192k",
        "-ac", "6",
        "-metadata:s:a:0", "title=Normalized 5.1",
        "-metadata:s:a:1", "title=Direct 5.1",
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-map_chapters", "-1",
        "-map_metadata", "-1",
        "-threads", "2",
        output_path
    ]
    
    # Debug: Print command for PowerShell
    print("\n📋 PowerShell Command:")
    print(" ".join(f'"{arg}"' for arg in cmd))
    
    # 4. Run FFmpeg
    try:
        # Run silently (stdout/stderr to DEVNULL) to keep console clean
        subprocess.run(cmd, check=True)
        
        if os.path.exists(output_path):
            print(f"   ✅ Upmix complete: {os.path.basename(output_path)}")
            os.remove(file_path) # Delete original stereo file
            return output_path   # Return NEW path
            
    except Exception as e:
        print(f"   ❌ Upmix failed: {e}")

        return file_path


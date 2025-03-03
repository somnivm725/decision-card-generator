from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

# For Pillow 10 and above, set ANTIALIAS to Resampling.LANCZOS if it isn't already defined.
if not hasattr(Image, 'ANTIALIAS'):
    try:
        # Pillow 10+ uses the Resampling enum.
        Image.ANTIALIAS = Image.Resampling.LANCZOS
    except AttributeError:
        # If for some reason Image.Resampling doesn't exist, fall back to Image.LANCZOS.
        Image.ANTIALIAS = Image.LANCZOS

import streamlit as st
from PIL import Image
import io
import numpy as np
import os
import tempfile
import json
import sys
import traceback
from moviepy.editor import (
    ImageClip, TextClip, ColorClip, CompositeVideoClip, 
    concatenate_videoclips, VideoFileClip, AudioFileClip, 
    concatenate_audioclips, VideoClip
)
from moviepy.config import change_settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from io import BytesIO
import subprocess

# Set title without debugging info
st.title("Decision Card Video Generator")

# Global counter for temp files
if 'file_counter' not in st.session_state:
    st.session_state.file_counter = 0

# Load saved entries from JSON file if it exists
SAVED_ENTRIES_FILE = "saved_entries.json"
if os.path.exists(SAVED_ENTRIES_FILE):
    with open(SAVED_ENTRIES_FILE, 'r', encoding='utf-8') as f:
        saved_entries = json.load(f)
else:
    saved_entries = {}

# Initialize session state
if 'saved_entries' not in st.session_state:
    st.session_state.saved_entries = saved_entries

# ImageMagick setup
IMAGEMAGICK_BINARY = os.getenv('IMAGEMAGICK_BINARY', 'C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe')
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})

# Dropdown to load saved entries
if st.session_state.saved_entries:
    selected_entry = st.selectbox(
        "Load saved entry:",
        ["New Entry"] + list(st.session_state.saved_entries.keys()),
        index=0
    )
    
    if selected_entry != "New Entry":
        entry_data = st.session_state.saved_entries[selected_entry]
        # Pre-fill form with saved data
        video_text = entry_data["video_text"]
        category = entry_data["category"]
        title = entry_data["title"]
        description = entry_data["description"]
        saved_choices = entry_data["choices"]
    else:
        # Default values for new entry
        video_text = ""
        category = ""
        title = ""
        description = ""
        saved_choices = []
else:
    selected_entry = "New Entry"
    # Default values
    video_text = ""
    category = ""
    title = ""
    description = ""
    saved_choices = []

# Top text for video
video_text = st.text_input("Video overlay text:", 
    value=video_text if 'video_text' in locals() else "Guys help I don't know which to pick")

# Card content inputs
col1, col2 = st.columns([2, 1])
with col1:
    category = st.text_input("Category:", 
        value=category if 'category' in locals() else "Lifestyle")
with col2:
    choices_length = len(saved_choices) if 'saved_choices' in locals() and saved_choices else 3
    num_choices = st.number_input("Number of choices:", 
        min_value=1, 
        max_value=5, 
        value=max(1, choices_length))  # Ensure minimum value is 1

title = st.text_input("Question:", 
    value=title if 'title' in locals() else "What pet should I get?")
description = st.text_input("Description:", 
    value=description if 'description' in locals() else "I want to have a lil companion")

# Container for choices and their pros/cons
choices = []

for i in range(int(num_choices)):
    st.subheader(f"Choice {i+1}")
    saved_choice = saved_choices[i] if 'saved_choices' in locals() and i < len(saved_choices) else None
    
    choice_name = st.text_input(f"Choice {i+1} name:", 
        value=saved_choice["name"] if saved_choice else "",
        key=f"choice_{i}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("Pros (one per line):")
        pros_text = st.text_area(f"Pros for choice {i+1}", 
            value="\n".join(saved_choice["pros"]) if saved_choice else "",
            key=f"pros_{i}", 
            height=150)
        pros = [p.strip() for p in pros_text.split('\n') if p.strip()]
    
    with col2:
        st.write("Cons (one per line):")
        cons_text = st.text_area(f"Cons for choice {i+1}", 
            value="\n".join(saved_choice["cons"]) if saved_choice else "",
            key=f"cons_{i}", 
            height=150)
        cons = [c.strip() for c in cons_text.split('\n') if c.strip()]
    
    choices.append({
        "name": choice_name,
        "pros": pros,
        "cons": cons
    })

# Audio upload
audio_file = st.file_uploader("Upload background music (m4a)", type=['m4a'])

# Background video upload
use_bg_video = st.checkbox("Use background video", value=False)
bg_video = None
if use_bg_video:
    bg_video = st.file_uploader("Upload background video (mp4)", type=['mp4'])

def create_card_html(category, title, description, active_choice, all_choices):
    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: rgb(0, 255, 0);
                overflow: hidden;
            }}
            /* Fix text rendering */
            * {{
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }}
            /* Ensure clean white text */
            .card-title {{
                color: white !important;
                text-shadow: none !important;
                mix-blend-mode: normal !important;
                background-color: transparent !important;
                -webkit-text-fill-color: white !important;
            }}
        </style>
    </head>
    <body>
        {create_card_html_body(category, title, description, active_choice, all_choices)}
    </body>
    </html>
    """
    return html

def create_card_html_body(category, title, description, active_choice, all_choices):
    html = f"""
    <div style="background: #16171a; width: 85%; border-radius: 30px; padding: 32px; margin: 250px auto 32px auto;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
            <div style="color: #5d89e2; font-family: 'Inter Tight', sans-serif; font-size: 36px; font-weight: 600;">{category}</div>
            <div style="display: flex; gap: 16px; align-items: center;">
                <div style="width: 52px; height: 52px; border-radius: 50%; border: 2px solid #39d2c0; background: transparent; display: flex; justify-content: center; align-items: center;">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" style="mix-blend-mode: normal;">
                        <path d="M12 2C9.243 2 7 4.243 7 7v3H6c-1.103 0-2 .897-2 2v8c0 1.103.897 2 2 2h12c1.103 0 2-.897 2-2v-8c0-1.103-.897-2-2-2h-1V7c0-2.757-2.243-5-5-5zm6 10v8H6v-8h12zm-9-2V7c0-1.654 1.346-3 3-3s3 1.346 3 3v3H9z" fill="white"/>
                    </svg>
                </div>
            </div>
        </div>
        
        <div class="card-title" style="font-family: 'Inter', sans-serif; font-size: 44px; font-weight: 600; margin-bottom: 12px; color: white !important; text-shadow: none !important; mix-blend-mode: normal !important; background-color: transparent !important; -webkit-text-fill-color: white !important;">{title}</div>
        <div style="color: #95a1ac; font-size: 36px; font-weight: 600; margin-bottom: 32px; font-family: 'Inter', sans-serif;">{description}</div>
        
        <div style="display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap;">
            {' '.join(f'''
            <div style="padding: 12px 24px; border-radius: 16px; font-family: 'Inter', sans-serif; font-size: 28px; font-weight: 500;
                background: #1b1a2f;
                border: {'2px solid #5d89e2' if choice['name'] == active_choice['name'] else 'none'};
                color: #95a1ac;">{choice['name']}</div>
            ''' for choice in all_choices)}
        </div>
        
        <div style="display: flex; margin-bottom: 24px;">
            <div style="font-family: 'Inter', sans-serif; font-size: 32px; color: #95a1ac; min-width: 120px; font-weight: 600;">Pros:</div>
            <div style="flex: 1;">
                {''.join(f'''
                <div style="margin-bottom: 12px; color: #95a1ac; font-size: 32px; font-family: Inter, sans-serif; font-weight: 500; display: flex;">
                    <span style="min-width: 20px; margin-right: 16px;">•</span>
                    <span style="flex: 1;">{pro}</span>
                </div>
                ''' for pro in active_choice['pros'])}
            </div>
        </div>

        <div style="display: flex;">
            <div style="font-family: 'Inter', sans-serif; font-size: 32px; color: #95a1ac; min-width: 120px; font-weight: 600;">Cons:</div>
            <div style="flex: 1;">
                 {''.join(f'''
                <div style="margin-bottom: 12px; color: #95a1ac; font-size: 32px; font-family: Inter, sans-serif; font-weight: 500; display: flex;">
                    <span style="min-width: 20px; margin-right: 16px;">•</span>
                    <span style="flex: 1;">{con}</span>
                </div>
                ''' for con in active_choice['cons'])}
            </div>
        </div>
    </div>
    """
    return html

def create_card_image(category, title, description, active_choice, all_choices):
    """Create a decision card directly as an image using PIL instead of HTML/Selenium."""
    # Create a transparent background
    width, height = 800, 1200
    card = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    
    # Card dimensions - make it larger to match the HTML version
    card_width = int(width * 0.85)
    card_x = (width - card_width) // 2
    card_y = 250
    card_height = 850  # Increased height for content
    
    # Draw the card background with rounded corners
    card_bg = Image.new('RGBA', (card_width, card_height), (22, 23, 26, 255))  # #16171a
    
    # Create a mask for rounded corners
    mask = Image.new('L', (card_width, card_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = 20
    mask_draw.rounded_rectangle([(0, 0), (card_width, card_height)], corner_radius, fill=255)
    
    # Paste the card background with rounded corners
    card.paste(card_bg, (card_x, card_y), mask)
    
    # Try to load fonts - use system fonts that are likely to be available on Windows
    try:
        # Try to find suitable fonts on the system
        category_font = ImageFont.truetype("Arial Bold", 36)
        title_font = ImageFont.truetype("Arial Bold", 44)
        desc_font = ImageFont.truetype("Arial Bold", 36)
        choice_font = ImageFont.truetype("Arial", 28)
        label_font = ImageFont.truetype("Arial Bold", 32)
        item_font = ImageFont.truetype("Arial", 32)
    except:
        # If we can't find the fonts, use the default
        try:
            # Try with just Arial which is more likely to be available
            category_font = ImageFont.truetype("Arial", 36)
            title_font = ImageFont.truetype("Arial", 44)
            desc_font = ImageFont.truetype("Arial", 36)
            choice_font = ImageFont.truetype("Arial", 28)
            label_font = ImageFont.truetype("Arial", 32)
            item_font = ImageFont.truetype("Arial", 32)
        except:
            # Last resort - use default font
            category_font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            desc_font = ImageFont.load_default()
            choice_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            item_font = ImageFont.load_default()
    
    # Draw category
    category_color = (93, 137, 226, 255)  # #5d89e2
    draw.text((card_x + 32, card_y + 32), category, font=category_font, fill=category_color)
    
    # Draw lock icon (simplified)
    lock_x = card_x + card_width - 84
    lock_y = card_y + 32
    lock_size = 52
    # Use pure white (255, 255, 255, 255) for the lock outline
    draw.ellipse([(lock_x, lock_y), (lock_x + lock_size, lock_y + lock_size)], outline=(255, 255, 255, 255), width=2)
    
    # Draw title
    # Use pure white (255, 255, 255, 255) for the title text
    title_color = (255, 255, 255, 255)  # Pure white
    draw.text((card_x + 32, card_y + 100), title, font=title_font, fill=title_color)
    
    # Draw description
    desc_color = (149, 161, 172, 255)  # #95a1ac
    desc_y = card_y + 170
    
    # Handle multiline description
    desc_lines = []
    words = description.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        text_width = draw.textlength(test_line, font=desc_font)
        
        if text_width <= card_width - 64:  # 32px padding on each side
            current_line = test_line
        else:
            desc_lines.append(current_line)
            current_line = word
    
    if current_line:
        desc_lines.append(current_line)
    
    # Draw each line of the description
    for i, line in enumerate(desc_lines):
        draw.text((card_x + 32, desc_y + i * 40), line, font=desc_font, fill=desc_color)
    
    # Update the y position for the next element
    choices_y = int(desc_y + len(desc_lines) * 40 + 40)  # Add some spacing
    
    # Draw choices
    choice_bg_color = (27, 26, 47, 255)  # #1b1a2f
    choice_active_border = (93, 137, 226, 255)  # #5d89e2
    
    choice_x = card_x + 32
    max_choice_y = choices_y  # Track the maximum y position
    
    for choice in all_choices:
        choice_text = choice['name']
        text_width = int(draw.textlength(choice_text, font=choice_font))
        text_height = int(choice_font.getbbox(choice_text)[3])
        
        # Draw choice background
        choice_width = int(text_width + 48)
        choice_height = int(text_height + 24)
        
        # Check if we need to wrap to the next line
        if choice_x + choice_width > card_x + card_width - 32:
            choice_x = card_x + 32
            choices_y += choice_height + 12
        
        # Create a mask for rounded corners
        choice_mask = Image.new('L', (choice_width, choice_height), 0)
        choice_mask_draw = ImageDraw.Draw(choice_mask)
        choice_mask_draw.rounded_rectangle([(0, 0), (choice_width, choice_height)], 16, fill=255)
        
        # Create the choice background
        choice_bg = Image.new('RGBA', (choice_width, choice_height), choice_bg_color)
        
        # If this is the active choice, add a border
        if choice['name'] == active_choice['name']:
            choice_border = Image.new('RGBA', (choice_width, choice_height), (0, 0, 0, 0))
            choice_border_draw = ImageDraw.Draw(choice_border)
            choice_border_draw.rounded_rectangle([(0, 0), (choice_width, choice_height)], 16, outline=choice_active_border, width=2)
            choice_bg = Image.alpha_composite(choice_bg, choice_border)
        
        # Paste the choice background
        card.paste(choice_bg, (choice_x, choices_y), choice_mask)
        
        # Draw choice text
        text_y = int(choices_y + (choice_height - text_height) // 2)
        draw.text((choice_x + 24, text_y), choice_text, font=choice_font, fill=desc_color)
        
        # Move to next choice
        choice_x += choice_width + 12
        max_choice_y = max(max_choice_y, choices_y + choice_height)
    
    # Move down for pros/cons
    content_y = int(max_choice_y + 40)
    
    # Draw pros
    draw.text((card_x + 32, content_y), "Pros:", font=label_font, fill=desc_color)
    item_y = content_y
    
    for pro in active_choice['pros']:
        item_y += 50
        # Draw bullet point
        draw.text((card_x + 152, item_y), "•", font=item_font, fill=desc_color)
        
        # Handle multiline pros
        pro_lines = []
        words = pro.split()
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            text_width = draw.textlength(test_line, font=item_font)
            
            if text_width <= card_width - 250:  # Account for indentation and padding
                current_line = test_line
            else:
                pro_lines.append(current_line)
                current_line = word
        
        if current_line:
            pro_lines.append(current_line)
        
        # Draw each line of the pro
        for i, line in enumerate(pro_lines):
            draw.text((card_x + 180, item_y + i * 40), line, font=item_font, fill=desc_color)
        
        # Update item_y for next pro
        item_y += (len(pro_lines) - 1) * 40
    
    # Draw cons
    cons_y = item_y + 80
    draw.text((card_x + 32, cons_y), "Cons:", font=label_font, fill=desc_color)
    item_y = cons_y
    
    for con in active_choice['cons']:
        item_y += 50
        # Draw bullet point
        draw.text((card_x + 152, item_y), "•", font=item_font, fill=desc_color)
        
        # Handle multiline cons
        con_lines = []
        words = con.split()
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            text_width = draw.textlength(test_line, font=item_font)
            
            if text_width <= card_width - 250:  # Account for indentation and padding
                current_line = test_line
            else:
                con_lines.append(current_line)
                current_line = word
        
        if current_line:
            con_lines.append(current_line)
        
        # Draw each line of the con
        for i, line in enumerate(con_lines):
            draw.text((card_x + 180, item_y + i * 40), line, font=item_font, fill=desc_color)
        
        # Update item_y for next con
        item_y += (len(con_lines) - 1) * 40
    
    # Ensure the card is tall enough for all content
    final_height = item_y + 80
    if final_height > card_y + card_height:
        # Create a new card background with the correct height
        new_card_height = final_height - card_y
        new_card_bg = Image.new('RGBA', (card_width, new_card_height), (22, 23, 26, 255))
        
        # Create a new mask for rounded corners
        new_mask = Image.new('L', (card_width, new_card_height), 0)
        new_mask_draw = ImageDraw.Draw(new_mask)
        new_mask_draw.rounded_rectangle([(0, 0), (card_width, new_card_height)], corner_radius, fill=255)
        
        # Create a new card
        new_card = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        # Paste the new background
        new_card.paste(new_card_bg, (card_x, card_y), new_mask)
        
        # Copy the original card content
        new_card.paste(card, (0, 0), card.split()[3])
        
        card = new_card
    
    return card

def create_video(images, text, audio_file=None, bg_video=None):
    try:
        # Disable progress bars to avoid stdout issues
        import proglog
        logger = proglog.TqdmProgressBarLogger(print_messages=False)
        
        # Basic settings
        duration_per_image = 1.5
        images = images[:3]  # Limit to first 3 images
        width, height = 1080, 1920
        total_duration = duration_per_image * len(images)
        
        # Create background - either from video or black
        background = None
        if bg_video:
            try:
                # Save uploaded video to temp file
                bg_temp = f"temp_bg_{st.session_state.file_counter}.mp4"
                st.session_state.file_counter += 1
                
                with open(bg_temp, "wb") as f:
                    f.write(bg_video.read())
                
                try:
                    # Load video
                    bg_clip = VideoFileClip(bg_temp)
                    
                    # Resize to match our dimensions
                    if bg_clip.w / bg_clip.h > width / height:
                        # Video is wider than our target
                        bg_clip = bg_clip.resize(height=height)
                        # Center crop
                        x_center = bg_clip.w // 2
                        bg_clip = bg_clip.crop(
                            x1=x_center - width//2,
                            y1=0,
                            x2=x_center + width//2,
                            y2=height
                        )
                    else:
                        # Video is taller than our target
                        bg_clip = bg_clip.resize(width=width)
                        # Center crop
                        y_center = bg_clip.h // 2
                        bg_clip = bg_clip.crop(
                            x1=0,
                            y1=y_center - height//2,
                            x2=width,
                            y2=y_center + height//2
                        )
                    
                    # Loop if needed
                    if bg_clip.duration < total_duration:
                        bg_clip = bg_clip.loop(duration=total_duration)
                    else:
                        bg_clip = bg_clip.subclip(0, total_duration)
                    
                    # Set as background
                    background = bg_clip
                except Exception as e:
                    st.error(f"Error processing video: {str(e)}")
            except Exception as e:
                st.error(f"Error saving video: {str(e)}")
        
        # Default to black background if video failed or wasn't provided
        if background is None:
            background = ColorClip(size=(width, height), 
                                  color=(0, 0, 0), 
                                  duration=total_duration)
        
        # Create clips for each image - COMPLETELY NEW APPROACH
        image_clips = []
        
        # Process each choice to create a card
        for idx, img in enumerate(images):
            # Create a new HTML for this card
            card_html = create_card_html_body(
                st.session_state.category,
                st.session_state.title,
                st.session_state.description,
                st.session_state.choices[idx],
                st.session_state.choices
            )
            
            # Create a temporary HTML file
            with tempfile.NamedTemporaryFile('w', suffix='.html', encoding='utf-8', delete=False) as f:
                f.write(f"""
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{
                            margin: 0;
                            padding: 0;
                            background-color: rgb(0, 255, 0);
                            overflow: hidden;
                        }}
                        /* Fix text rendering */
                        * {{
                            -webkit-font-smoothing: antialiased;
                            -moz-osx-font-smoothing: grayscale;
                        }}
                        /* Ensure clean white text */
                        .card-title {{
                            color: white !important;
                            text-shadow: none !important;
                            mix-blend-mode: normal !important;
                            background-color: transparent !important;
                            -webkit-text-fill-color: white !important;
                        }}
                    </style>
                </head>
                <body>
                    {card_html}
                </body>
                </html>
                """)
                temp_html_path = f.name
            
            # Create a temporary PNG file for the output
            temp_png_path = f"temp_card_{idx}.png"
            
            # Use wkhtmltoimage to render the HTML to PNG with transparency
            try:
                # Try to use wkhtmltoimage if available
                subprocess.run([
                    "wkhtmltoimage",
                    "--transparent",
                    "--width", "800",
                    "--height", "1200",
                    temp_html_path,
                    temp_png_path
                ], check=True)
                
                # Load the image
                card_img = ImageClip(temp_png_path)
                
            except (subprocess.SubprocessError, FileNotFoundError):
                # If wkhtmltoimage fails or is not available, use our HTML renderer
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--hide-scrollbars")
                chrome_options.add_argument("--force-device-scale-factor=1")
                chrome_options.add_argument("--disable-gpu")
                
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_window_size(800, 1200)
                
                # Load the HTML
                driver.get(f'file:///{temp_html_path}')
                driver.implicitly_wait(2)
                
                # Take a screenshot
                driver.save_screenshot(temp_png_path)
                driver.quit()
                
                # Load the image and make the green background transparent
                card_img = Image.open(temp_png_path)
                
                # Convert green background to transparent
                card_img = card_img.convert("RGBA")
                datas = card_img.getdata()
                
                new_data = []
                for item in datas:
                    # Change only green background pixels to transparent
                    # This is a specific green color that won't affect white text
                    if item[0] < 50 and item[1] > 200 and item[2] < 50:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)
                
                card_img.putdata(new_data)
                card_img.save(temp_png_path, "PNG")
                
                # Create the clip
                card_img = ImageClip(temp_png_path)
            
            # Position the card in the center of the frame
            card_img = card_img.set_position(('center', 400))
            
            # Set the duration and start time
            card_img = card_img.set_start(duration_per_image * idx)
            card_img = card_img.set_duration(duration_per_image)
            
            # Add fade-in effect with delay for the first card
            if idx == 0:
                # Add a 0.5 second delay before the first card appears
                card_img = card_img.set_start(0.5)
                # Add a 0.8 second fade-in effect
                card_img = card_img.fadein(0.8)
            
            # Add to clips
            image_clips.append(card_img)
            
            # Clean up the temporary HTML file
            try:
                os.unlink(temp_html_path)
            except:
                pass
        
        # Create text clip if text is provided
        if text:
            txt_clip = TextClip(
                text,
                fontsize=55,
                color='white',
                method='caption',
                size=(width-150, None),
                align='center'
            )
            # Position text above the cards (at the top area of the screen)
            txt_clip = txt_clip.set_position(('center', 375))
            txt_clip = txt_clip.set_duration(total_duration)
            image_clips.append(txt_clip)
        
        # Combine all clips
        all_clips = [background] + image_clips
        video = CompositeVideoClip(all_clips, size=(width, height))
        
        # Add audio if provided
        if audio_file:
            # Save uploaded audio to temp file
            audio_temp = f"temp_audio_{st.session_state.file_counter}.mp3"
            st.session_state.file_counter += 1
            
            with open(audio_temp, "wb") as f:
                f.write(audio_file.read())
            
            # Load audio
            audio = AudioFileClip(audio_temp)
            
            # Loop audio if it's shorter than video
            if audio.duration < total_duration:
                repeats = int(np.ceil(total_duration / audio.duration))
                audio = concatenate_audioclips([audio] * repeats)
            
            # Trim audio to match video duration
            audio = audio.subclip(0, total_duration)
            video = video.set_audio(audio)
        
        # Write video to file
        output_file = "output_video.mp4"
        video.write_videofile(
            output_file,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            logger=logger,
            verbose=False
        )
        
        # Clean up temporary files
        for idx in range(len(images)):
            temp_png_path = f"temp_card_{idx}.png"
            if os.path.exists(temp_png_path):
                try:
                    os.unlink(temp_png_path)
                except:
                    pass
        
        return output_file
        
    except Exception as e:
        st.error(f"Error creating video: {str(e)}")
        st.error(f"Traceback: {traceback.format_exc()}")
        return None

def create_decision_video(output_file):
    try:
        # Disable progress bars to avoid stdout issues
        import proglog
        logger = proglog.TqdmProgressBarLogger(print_messages=False)
        
        # Create clips
        clips = []
        
        # Add intro clip
        intro_clip = create_intro_clip()
        clips.append(intro_clip)
        
        # Add card clips
        for i, choice in enumerate(st.session_state.choices):
            card_clip = create_card_clip(
                i + 1,
                choice["text"],
                choice.get("pros", []),
                choice.get("cons", [])
            )
            clips.append(card_clip)
        
        # Add final decision clip
        final_decision_clip = create_final_decision_clip()
        clips.append(final_decision_clip)
        
        # Concatenate clips
        video = concatenate_videoclips(clips)
        
        # Write video file with logger to avoid stdout issues
        video.write_videofile(
            output_file,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            logger=logger,
            verbose=False
        )
        
        return True, "Video created successfully!"
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return False, f"Error creating video: {str(e)}\n\nTraceback: {error_details}"

def save_decision_entry(category, title, description, choices):
    """Save a decision entry to the saved entries file."""
    entry_data = {
        "category": category,
        "title": title,
        "description": description,
        "choices": choices
    }
    
    # Use title as the key
    st.session_state.saved_entries[title] = entry_data
    
    # Save to file
    with open(SAVED_ENTRIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.saved_entries, f, ensure_ascii=False, indent=2)

save_entry = st.checkbox("Save this entry for future use", value=False)

if st.button("Generate Video"):
    if not all(choice['name'] for choice in choices):
        st.error("All choices must have a name")
    else:
        with st.spinner("Generating video..."):
            try:
                # Store the current values in session state so they can be accessed in the video creation function
                st.session_state.category = category
                st.session_state.title = title
                st.session_state.description = description
                st.session_state.choices = choices
                
                # Generate images for each choice
                images = []
                for choice in choices:
                    if choice['name']:  # Only process choices with names
                        # Create card image directly without HTML/Selenium
                        img = create_card_image(
                            category,
                            title,
                            description,
                            choice,
                            choices
                        )
                        images.append(img)
                
                # Create video
                output_file = create_video(images, video_text, audio_file, bg_video)
                
                if output_file:
                    # Display video
                    st.video(output_file)
                    
                    # Provide download button
                    with open(output_file, "rb") as file:
                        btn = st.download_button(
                            label="Download Video",
                            data=file,
                            file_name="decision_card_video.mp4",
                            mime="video/mp4"
                        )
                    
                    # Save entry if requested
                    if save_entry:
                        save_decision_entry(category, title, description, choices)
                        st.success("Entry saved successfully!")
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.error(traceback.format_exc())
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import requests
import time
from typing import Optional, Dict, Any, List, Tuple
import logging
import tempfile
import os
from gtts import gTTS
import numpy as np
import streamlit as st

class MarketingVideoGenerator:
    def __init__(self, aria_api_key: str, aria_base_url: str, allegro_token: str):
        self.allegro_token = allegro_token
        self.chat = ChatOpenAI(
            model="aria",
            api_key=aria_api_key,
            base_url=aria_base_url,
            streaming=False,
            stop=["<|im_end|>"]
        )
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        self.temp_dir = tempfile.mkdtemp()
        self.SEGMENT_DURATION = 6  # seconds
        self.TOTAL_SEGMENTS = 3    # 3 segments for 18 seconds total
        self.VIDEO_GENERATION_WAIT = 120  # 2 minutes minimum wait

    def analyze_content(self, content: str) -> Dict[str, List[str]]:
        """
        Analyze content to generate three 6-second scene descriptions and voiceover scripts.
        """
        system_prompt = """You are a dual-expert in visual direction and marketing. Create three 6-second segments, each with:

        1. Visual Scene Descriptions:
        Generate three distinct 6-second scene descriptions that Allegro can use. Each should:
        - Be visually compelling and clear
        - Flow naturally from one to the next
        - Should have enough context to get independently generated
        - Be achievable by AI generation
        
        2. Marketing Voiceover Scripts:
        Create three 6-second voiceover segments that:
        - Match their corresponding visuals
        - Form a cohesive marketing message
        - Have natural timing and pacing
        
        Format your response exactly as:
        Scene Description 1: [first 6-second visual scene]
        Voiceover Script 1:
        [First segment script]

        Scene Description 2: [second 6-second visual scene]
        Voiceover Script 2:
        [Second segment script]

        Scene Description 3: [third 6-second visual scene]
        Voiceover Script 3:
        [Third segment script]"""

        try:
            response = self.chat.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=content)
            ])
            
            content = response.content
            segments = []
            voiceovers = []
            
            # Parse each segment
            for i in range(1, 4):
                scene_start = content.find(f"Scene Description {i}:")
                scene_end = content.find(f"Voiceover Script {i}:")
                next_segment = content.find(f"Scene Description {i+1}:") if i < 3 else len(content)
                
                scene_desc = content[scene_start:scene_end].split(":", 1)[1].strip()
                voiceover = content[scene_end:next_segment].split(":", 1)[1].strip()
                
                segments.append(scene_desc)
                voiceovers.append(voiceover)
            
            return {
                'scene_descriptions': segments,
                'voiceover_scripts': voiceovers
            }
        except Exception as e:
            self.logger.error(f"Error in content analysis: {str(e)}")
            raise

    def generate_video_segment(self, prompt: str) -> Dict[str, Any]:
        print("creating video for ", prompt)
        """Generate a 6-second video segment using Allegro API"""
        url = "https://api.rhymes.ai/v1/generateVideoSyn"
        headers = {
            "Authorization": f"Bearer {self.allegro_token}",
            "Content-Type": "application/json"
        }
        data = {
            "refined_prompt": prompt,
            "num_step": 100,
            "cfg_scale": 7.5,
            "user_prompt": prompt,
            "rand_seed": 12345
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            print("response is")
            print(response.json())
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error in video generation: {str(e)}")
            raise

    def check_video_status(self, request_id: str) -> Dict[str, Any]:
        """
        Check the status of a video generation request.
        
        Args:
            request_id: The ID of the video generation request
            
        Returns:
            Dict containing status information
        """
        url = "https://api.rhymes.ai/v1/videoQuery"
        headers = {"Authorization": f"Bearer {self.allegro_token}"}
        params = {"requestId": request_id}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            response = response.json()
            if "data" in response.keys() and response['data']!='':
              response["status"]="completed"
            else:
              response["status"]="pending"
            return response  
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error checking video status: {str(e)}")
            raise

    def wait_for_video_completion(self, request_id: str) -> str:
        """Wait for video generation to complete with minimum wait time"""
        print(f"waiting for {request_id}")
        start_time = time.time()
        
        # First, wait the minimum required time
        time.sleep(self.VIDEO_GENERATION_WAIT)
        
        # Then start checking status
        while True:
            try:
                status_response = self.check_video_status(request_id)
                if status_response.get('status') == 'completed':
                    print(f"The video for {request_id} got completed")
                    print(status_response)
                    return

                # Check if we've waited too long (e.g., 5 minutes)
                if time.time() - start_time > 300:
                    raise TimeoutError("Video generation timed out")
                
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                self.logger.error(f"Error checking video status: {str(e)}")
                raise

    def get_video_url(self, request_id: str) -> str:
        """Wait for video generation to complete with minimum wait time"""
        print(f"getting url for {request_id}")
        start_time = time.time()
        
        # Then start checking status
        while True:
            try:
                status_response = self.check_video_status(request_id)
                if status_response.get('status') == 'completed':
                    print(f"The video for {request_id} got completed")
                    return status_response["data"]
                
                # Check if we've waited too long (e.g., 5 minutes)
                if time.time() - start_time > 300:
                    raise TimeoutError("Video generation timed out")
                
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                self.logger.error(f"Error checking video status: {str(e)}")
                raise

    def generate_segment_audio(self, script: str, index: int) -> str:
        """Generate audio for a single segment"""
        try:
            audio_path = os.path.join(self.temp_dir, f'voiceover_{index}.mp3')
            tts = gTTS(text=script, lang='en', slow=False)
            tts.save(audio_path)
            return audio_path
        except Exception as e:
            self.logger.error(f"Error in audio generation: {str(e)}")
            raise

    def add_text_to_frame(self, frame: np.ndarray, text: str) -> np.ndarray:
        """Add text overlay to a single frame"""
        # Convert CV2 frame to PIL Image
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        
        # Create draw object
        draw = ImageDraw.Draw(pil_image)
        
        # Get frame dimensions
        img_w, img_h = pil_image.size
        
        # Set font size
        fontsize = 30
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fontsize)
        except:
            font = ImageFont.load_default()

        # Get text size
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Calculate text position (centered, near bottom)
        x = (img_w - text_width) // 2
        y = img_h - text_height - 50
        
        # Draw semi-transparent background
        padding = 10
        bg_bbox = [
            x - padding,
            y - padding,
            x + text_width + padding,
            y + text_height + padding
        ]
        draw.rectangle(bg_bbox, fill=(0, 0, 0, 128))
        
        # Draw text
        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        
        # Convert back to CV2 format
        frame_with_text = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return frame_with_text

    def combine_segments(self, video_paths: List[str], audio_paths: List[str], 
                        scripts: List[str], output_path: str) -> str:
        """Combine multiple segments into final video"""
        try:
            # Create temporary directory for processing
            temp_video_segments = []
            
            # Process each segment
            for i, (video_path, audio_path, script) in enumerate(zip(video_paths, audio_paths, scripts)):

                print(f"Processing segment {i}")
                print(video_path,audio_path, script)
                
                # Download video
                response = requests.get(video_path)
                temp_video_dir = tempfile.gettempdir()
                temp_video_path = os.path.join(temp_video_dir, f"downloaded_video_{i}.mp4")
                #temp_video_path = f"/content/downloaded_video_12{i}.mp4"
                os.makedirs(os.path.dirname(temp_video_path), exist_ok=True)

                with open(temp_video_path, "wb") as f:
                    f.write(response.content)
                
                # Open video
                cap = cv2.VideoCapture(temp_video_path)
                fps = int(cap.get(cv2.CAP_PROP_FPS))
                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                # Create temporary output video for this segment
                temp_output = os.path.join(self.temp_dir, f'segment_{i}.mp4')
                out = cv2.VideoWriter(temp_output, 
                                    cv2.VideoWriter_fourcc(*'mp4v'),
                                    fps, (frame_width, frame_height))
                
                # Process each frame
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Add text overlay
                    frame_with_text = self.add_text_to_frame(frame, script)
                    out.write(frame_with_text)
                
                cap.release()
                out.release()
                
                # Convert video to format compatible with audio
                temp_output_with_audio = os.path.join(self.temp_dir, f'segment_with_audio_{i}.mp4')
                os.system(f'ffmpeg -i {temp_output} -c:v libx264 {temp_output_with_audio}')
                
                # Add audio using ffmpeg
                final_segment = os.path.join(self.temp_dir, f'final_segment_{i}.mp4')
                os.system(f'ffmpeg -i {temp_output_with_audio} -i {audio_path} -c:v copy -c:a aac {final_segment}')
                
                temp_video_segments.append(final_segment)
                
                # Clean up temporary files
                os.remove(temp_video_path)
                os.remove(temp_output)
                os.remove(temp_output_with_audio)
            
            # Combine all segments
            # Create file list for ffmpeg
            with open('file_list.txt', 'w') as f:
                for segment in temp_video_segments:
                    f.write(f"file '{segment}'\n")
            
            # Concatenate using ffmpeg
            os.system(f'ffmpeg -y -f concat -safe 0 -i file_list.txt -c copy {output_path}')
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Error in video combination: {str(e)}")
            raise
        finally:
            # Clean up
            try:
                os.remove('file_list.txt')
                for segment in temp_video_segments:
                    os.remove(segment)
            except:
                pass

    def create_marketing_video(self, input_content: str, output_path: str) -> Dict[str, Any]:
        """
        Create complete marketing video from three 5-second segments.
        """
        try:
            # # Step 1: Generate all scene descriptions and scripts


            content_analysis = self.analyze_content(input_content)
            scenes = content_analysis['scene_descriptions']
            scripts = content_analysis['voiceover_scripts']

            # scenes = ['A bustling office environment with employees working at high-speed, papers flying, and phones ringing. Suddenly, the pace slows as an AI-powered screen with the company logo appears, seamlessly integrating into the workflow with a click.', 'The same office, now calm and orderly, with employees smiling and collaborating over tasks completed with ease. The AI system is subtly featured in the background, processing data effortlessly.', "A montage of diverse business professionals from various industries, all experiencing the same smoothness and productivity boost. The company's product is showcased as the central tool behind their success."]
            # scripts = ['[0s] "Efficiency is key in today\'s fast-paced business world."', '[5s] "Our new solution automates the mundane, freeing your team for innovation."', '[10s] "Join the revolution. Let technology elevate your business."']
            print("scenes are")
            print(scenes)
            print("scripts are")
            print(scripts)
            
            # Step 2: Initialize video generation for all segments concurrently
            video_requests = []
            for scene in scenes:
                request = self.generate_video_segment(scene)
                if 'data' not in request.keys():
                  print("Not got request id")
                  raise
                
                video_requests.append(request.get('data'))
                self.wait_for_video_completion(video_requests[-1])
                if(len(video_requests)>2):
                    break
                print("waiting for 20 seconds")
                time.sleep(20)
            
            # Step 3: Wait for all videos to complete (minimum 2 minutes each)
            video_paths = []
            for i, request_id in enumerate(video_requests):
                self.logger.info(f"Waiting for video segment {i+1} to complete...")
                print(f"Waiting for video segment {i+1} to complete...")
                video_url = self.get_video_url(request_id)
                video_paths.append(video_url)

            # video_paths = ['https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103015632.mp4','https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103020054.mp4','https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103020516.mp4']
            
            # Step 4: Generate audio for all segments
            audio_paths = []
            for i, script in enumerate(scripts):
                audio_path = self.generate_segment_audio(script, i)
                audio_paths.append(audio_path)

            print("Audio Files are")
            print(audio_paths)

            # Step 5: Combine all segments
            final_path = self.combine_segments(
                video_paths, audio_paths, scripts, output_path
            )
            
            return {
                'status': 'success',
                'final_video_path': final_path,
                'content_analysis': content_analysis
            }
            
        except Exception as e:
            self.logger.error(f"Error in marketing video creation: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
        finally:
            # Cleanup temporary files
            self.cleanup_temp_files()

    def cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            for file in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, file))
            os.rmdir(self.temp_dir)
        except Exception as e:
            self.logger.error(f"Error cleaning up temporary files: {str(e)}")


if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'status_message' not in st.session_state:
    st.session_state.status_message = ""
if 'video_path' not in st.session_state:
    st.session_state.video_path = None

def update_status(message, progress):
    st.session_state.status_message = message
    st.session_state.progress = progress
    status_text.text(message)
    progress_bar.progress(progress)

# Streamlit UI
st.title("Marketing Video Generator")

# API Configuration
with st.sidebar:
    st.header("API Configuration")
    aria_api_key = st.text_input("Aria API Key", type="password")
    aria_base_url = st.text_input("Aria Base URL")
    allegro_token = st.text_input("Allegro Token", type="password")

# Main content area
content_input = st.text_area("Enter your marketing content:", height=150)
generate_button = st.button("Generate Video")

# Progress tracking elements
progress_bar = st.progress(0)
status_text = st.empty()

if generate_button and content_input:
    try:
        # Initialize the video generator
        generator = MarketingVideoGenerator(
            aria_api_key=aria_api_key,
            aria_base_url=aria_base_url,
            allegro_token=allegro_token
        )
        
        # Create temporary output path
        output_path = os.path.join(tempfile.gettempdir(), "final_marketing_video.mp4")
        
        # Step 1: Content Analysis
        update_status("Analyzing content and generating scripts...", 10)
        content_analysis = generator.analyze_content(content_input)

        # Uncomment below 3 lines if wish to skip video generation time

        # content_analysis={}
        # content_analysis['scene_descriptions'] = ['A bustling office environment with employees working at high-speed, papers flying, and phones ringing. Suddenly, the pace slows as an AI-powered screen with the company logo appears, seamlessly integrating into the workflow with a click.', 'The same office, now calm and orderly, with employees smiling and collaborating over tasks completed with ease. The AI system is subtly featured in the background, processing data effortlessly.', "A montage of diverse business professionals from various industries, all experiencing the same smoothness and productivity boost. The company's product is showcased as the central tool behind their success."]
        # content_analysis['voiceover_scripts'] = ["Efficiency is key in today\'s fast-paced business world.", "Our new solution automates the mundane, freeing your team for innovation.",  "Join the revolution. Let technology elevate your business."]
           
        # Display generated content
        with st.expander("View Generated Scripts"):
            for i, (scene, script) in enumerate(zip(
                content_analysis['scene_descriptions'],
                content_analysis['voiceover_scripts']
            )):
                st.write(f"Scene {i+1}:")
                st.write(f"Description: {scene}")
                st.write(f"Script: {script}")
                st.write("---")
        
        # Step 2: Video Generation

        # Comment below 2 For Loops if wish to skip video generation time
        video_requests = []
        for i, scene in enumerate(content_analysis['scene_descriptions']):
            update_status(f"Generating video segment {i+1}/3...", 20 + i*10)
            request = generator.generate_video_segment(scene)
            video_requests.append(request.get('data'))
            generator.wait_for_video_completion(video_requests[-1])
            if(i<2):
                st.write("Waiting for 20 seconds")
                time.sleep(20)
        
        # Step 3: Wait for videos and get URLs
        video_paths = []
        for i, request_id in enumerate(video_requests):
            update_status(f"Processing video segment {i+1}/3...", 50 + i*10)
            video_url = generator.get_video_url(request_id)
            video_paths.append(video_url)
        
        # Step 4: Generate Audio

        # Uncomment below 1 line if wish to skip video generation time

        #video_paths = ['https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103015632.mp4','https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103020054.mp4','https://apiplatform-rhymes-prod-va.s3.amazonaws.com/20241103020516.mp4']
        
        update_status("Generating audio segments...", 80)
        audio_paths = []
        for i, script in enumerate(content_analysis['voiceover_scripts']):
            audio_path = generator.generate_segment_audio(script, i)
            audio_paths.append(audio_path)
        
        # Step 5: Combine Segments
        update_status("Combining video and audio segments...", 90)
        result = generator.combine_segments(
            video_paths,
            audio_paths,
            content_analysis['voiceover_scripts'],
            output_path
        )
        
        # Final step: Show download button
        update_status("Video generation complete!", 100)
        
        # Read the video file
        with open(output_path, 'rb') as video_file:
            video_bytes = video_file.read()
        
        # Create download button
        st.download_button(
            label="Download Video",
            data=video_bytes,
            file_name="marketing_video.mp4",
            mime="video/mp4"
        )
        
        # Optional: Display the video
        st.video(video_bytes)
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        update_status("Error occurred during video generation", 0)
    
    finally:
        # Cleanup
        generator.cleanup_temp_files()

# Display current status
if st.session_state.status_message:
    status_text.text(st.session_state.status_message)
    progress_bar.progress(st.session_state.progress)
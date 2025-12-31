"""
AWS S3 Storage and Automated Content Processing
Handles file uploads, transcription, and quote extraction at scale
"""
import os
import boto3
from botocore.exceptions import ClientError
import openai
from pathlib import Path
import json
from typing import List, Dict, Optional
import tempfile
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContentProcessor:
    """Automated content processing pipeline with AWS S3 storage"""
    
    def __init__(self):
        # AWS S3 Configuration
        self.s3_client = None
        self.bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
        
        # Initialize S3 if credentials are available
        if all([
            os.getenv('AWS_ACCESS_KEY_ID'),
            os.getenv('AWS_SECRET_ACCESS_KEY'),
            self.bucket_name
        ]):
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                    region_name=os.getenv('AWS_REGION', 'us-east-1')
                )
                logger.info(f"✅ AWS S3 initialized: {self.bucket_name}")
            except Exception as e:
                logger.warning(f"⚠️ AWS S3 initialization failed: {e} - using local storage")
                self.s3_client = None
        else:
            logger.info("ℹ️ AWS S3 not configured - using local storage")
        
        # OpenAI Configuration - simple initialization
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
            logger.info("✅ OpenAI API initialized")
    
    def upload_to_s3(self, file_path: str, object_name: str = None) -> Optional[str]:
        """
        Upload file to AWS S3
        
        Args:
            file_path: Local file path
            object_name: S3 object name (if None, uses file name)
            
        Returns:
            S3 URL if successful, None otherwise
        """
        if not self.s3_client:
            logger.warning("S3 not configured - file stored locally")
            return None
        
        if object_name is None:
            object_name = os.path.basename(file_path)
        
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            s3_url = f"s3://{self.bucket_name}/{object_name}"
            logger.info(f"✅ Uploaded to S3: {s3_url}")
            return s3_url
        except ClientError as e:
            logger.error(f"❌ S3 upload failed: {e}")
            return None
    
    def download_from_s3(self, object_name: str, local_path: str) -> bool:
        """Download file from S3 to local path"""
        if not self.s3_client:
            return False
        
        try:
            self.s3_client.download_file(self.bucket_name, object_name, local_path)
            logger.info(f"✅ Downloaded from S3: {object_name}")
            return True
        except ClientError as e:
            logger.error(f"❌ S3 download failed: {e}")
            return False
    
    def split_audio_file(self, file_path: str, chunk_duration: int = 600) -> List[str]:
        """
        Split large audio file into smaller chunks
        
        Args:
            file_path: Path to audio file
            chunk_duration: Duration of each chunk in seconds (default: 10 minutes)
            
        Returns:
            List of chunk file paths
        """
        try:
            logger.info(f"✂️ Splitting audio file into {chunk_duration}s chunks...")
            
            # Use pydub for audio splitting
            try:
                from pydub import AudioSegment
            except ImportError:
                logger.error("pydub not installed. Install with: pip install pydub")
                return []
            
            # Load audio file
            audio = AudioSegment.from_file(file_path)
            
            # Calculate number of chunks
            duration_ms = len(audio)
            chunk_duration_ms = chunk_duration * 1000
            num_chunks = (duration_ms // chunk_duration_ms) + 1
            
            logger.info(f"📊 Total duration: {duration_ms / 1000 / 60:.1f} minutes")
            logger.info(f"📦 Splitting into {num_chunks} chunks of {chunk_duration / 60:.0f} minutes each")
            
            # Create chunks directory
            chunks_dir = Path(file_path).parent / "chunks"
            chunks_dir.mkdir(exist_ok=True)
            
            # Split into chunks
            chunk_paths = []
            for i in range(num_chunks):
                start_ms = i * chunk_duration_ms
                end_ms = min((i + 1) * chunk_duration_ms, duration_ms)
                
                chunk = audio[start_ms:end_ms]
                chunk_filename = f"{Path(file_path).stem}_chunk_{i+1}.mp3"
                chunk_path = chunks_dir / chunk_filename
                
                # Export chunk
                chunk.export(str(chunk_path), format="mp3", bitrate="64k")
                chunk_paths.append(str(chunk_path))
                
                chunk_size = os.path.getsize(chunk_path) / 1024 / 1024
                logger.info(f"✅ Created chunk {i+1}/{num_chunks}: {chunk_size:.2f} MB")
            
            return chunk_paths
            
        except Exception as e:
            logger.error(f"❌ Failed to split audio: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def transcribe_audio(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio/video file using OpenAI Whisper
        Automatically splits large files (>25MB) into chunks
        
        Args:
            file_path: Path to audio/video file
            
        Returns:
            Transcription text or None
        """
        try:
            logger.info(f"🎤 Transcribing: {file_path}")
            
            # Check file exists and size
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.error(f"❌ File is empty: {file_path}")
                return None
            
            file_size_mb = file_size / 1024 / 1024
            logger.info(f"📊 File size: {file_size_mb:.2f} MB")
            
            # Check if file needs to be split (25MB Whisper limit)
            MAX_SIZE_MB = 24.5  # Use 24.5 to be safe
            
            if file_size_mb > MAX_SIZE_MB:
                logger.warning(f"⚠️ File is larger than {MAX_SIZE_MB}MB - splitting into chunks...")
                
                # Split the file
                chunk_paths = self.split_audio_file(file_path, chunk_duration=600)  # 10-minute chunks
                
                if not chunk_paths:
                    logger.error("❌ Failed to split file")
                    return None
                
                # Transcribe each chunk
                transcripts = []
                for i, chunk_path in enumerate(chunk_paths, 1):
                    logger.info(f"🎤 Transcribing chunk {i}/{len(chunk_paths)}...")
                    
                    chunk_size = os.path.getsize(chunk_path) / 1024 / 1024
                    logger.info(f"📊 Chunk size: {chunk_size:.2f} MB")
                    
                    with open(chunk_path, 'rb') as audio_file:
                        from openai import OpenAI
                        client = OpenAI(
                            api_key=self.openai_api_key,
                            timeout=600.0,
                            max_retries=2
                        )
                        
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="text"
                        )
                        
                        transcripts.append(transcript)
                        logger.info(f"✅ Chunk {i} transcribed: {len(transcript)} characters")
                
                # Combine all transcripts
                full_transcript = " ".join(transcripts)
                logger.info(f"✅ All chunks transcribed! Total: {len(full_transcript)} characters")
                
                # Clean up chunk files
                for chunk_path in chunk_paths:
                    try:
                        os.remove(chunk_path)
                    except:
                        pass
                
                return full_transcript
            
            else:
                # File is small enough - transcribe directly
                with open(file_path, 'rb') as audio_file:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=self.openai_api_key,
                        timeout=600.0,
                        max_retries=2
                    )
                    
                    logger.info("🔄 Sending to Whisper API...")
                    
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="text"
                    )
                
                logger.info(f"✅ Transcription complete: {len(transcript)} characters")
                return transcript
            
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def extract_quotes(self, text: str, num_quotes: int = 10, source: str = None) -> List[Dict]:
        """
        Extract quotes from text using GPT-4
        
        Args:
            text: Text content to analyze
            num_quotes: Number of quotes to extract
            source: Source attribution (e.g., "Minister Farrakhan")
            
        Returns:
            List of quote dictionaries
        """
        try:
            logger.info(f"💭 Extracting {num_quotes} quotes from {len(text)} characters")
            
            # Initialize OpenAI client with minimal config
            from openai import OpenAI
            client = OpenAI(
                api_key=self.openai_api_key,
                timeout=120.0,
                max_retries=2
            )
            
            # Limit text to avoid token limits
            text_sample = text[:8000] if len(text) > 8000 else text
            
            prompt = f"""Extract {num_quotes} powerful, meaningful quotes from this Nation of Islam content.
            
Focus on:
- Wisdom and knowledge
- Empowerment and self-improvement
- Unity and community
- Faith and spirituality
- Justice and truth

Content:
{text_sample}

Return ONLY a JSON array with this exact format:
[
  {{
    "quote_text": "the quote here",
    "author": "attribution if mentioned, otherwise '{source or 'Unknown'}'",
    "category": "one of: wisdom, faith, unity, empowerment, knowledge, justice"
  }}
]

Make quotes concise (under 280 characters for Twitter). Extract the most powerful statements."""

            logger.info("🔄 Sending to GPT-4...")
            
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at identifying powerful, meaningful quotes from religious and educational content. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            # Clean up the response - remove markdown code blocks if present
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            try:
                quotes = json.loads(content)
                
                # Ensure it's a list
                if isinstance(quotes, dict):
                    quotes = quotes.get('quotes', [])
                
                logger.info(f"✅ Extracted {len(quotes)} quotes")
                return quotes
                
            except json.JSONDecodeError as je:
                logger.error(f"Failed to parse JSON response: {je}")
                logger.error(f"Response content: {content[:500]}")
                return []
            
        except Exception as e:
            logger.error(f"❌ Quote extraction failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def read_text_file(self, file_path: str) -> Optional[str]:
        """Read text from various file formats"""
        try:
            file_ext = Path(file_path).suffix.lower()
            
            # Plain text files
            if file_ext in ['.txt', '.md']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            # PDF files
            elif file_ext == '.pdf':
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text()
                    return text
                except ImportError:
                    logger.warning("PyPDF2 not installed - install with: pip install PyPDF2")
                    return None
            
            # Word documents
            elif file_ext in ['.doc', '.docx']:
                try:
                    import docx
                    doc = docx.Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])
                    return text
                except ImportError:
                    logger.warning("python-docx not installed - install with: pip install python-docx")
                    return None
            
            else:
                logger.warning(f"Unsupported text format: {file_ext}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return None
    
    def process_file(
        self,
        file_path: str,
        file_type: str,
        source: str = None,
        num_quotes: int = 10,
        upload_to_s3: bool = True
    ) -> Dict:
        """
        Complete pipeline: Process a file and extract quotes
        
        Args:
            file_path: Path to file
            file_type: 'video', 'audio', 'text'
            source: Source attribution
            num_quotes: Number of quotes to extract
            upload_to_s3: Whether to upload to S3
            
        Returns:
            Dictionary with processing results
        """
        result = {
            'success': False,
            'file_path': file_path,
            'file_type': file_type,
            's3_url': None,
            'transcription': None,
            'quotes': [],
            'error': None
        }
        
        try:
            # Step 1: Upload to S3 (optional)
            if upload_to_s3 and self.s3_client:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_ext = Path(file_path).suffix  # Get file extension (.mp3, .mp4, etc.)
                filename = Path(file_path).stem  # Get filename without extension
                s3_key = f"noi_content/{timestamp}_{filename}{file_ext}"  # Include extension
                result['s3_url'] = self.upload_to_s3(file_path, s3_key)
                logger.info(f"📁 File uploaded to S3: {s3_key}")
            elif upload_to_s3 and not self.s3_client:
                logger.info("ℹ️ S3 not configured - file stored locally only")
            
            # Step 2: Get text content
            text_content = None
            
            if file_type in ['video', 'audio']:
                # Transcribe audio/video
                text_content = self.transcribe_audio(file_path)
                result['transcription'] = text_content
            
            elif file_type == 'text':
                # Read text file
                text_content = self.read_text_file(file_path)
                result['transcription'] = text_content
            
            if not text_content:
                result['error'] = "Failed to extract text content"
                return result
            
            # Step 3: Extract quotes
            quotes = self.extract_quotes(text_content, num_quotes, source)
            result['quotes'] = quotes
            
            # Success!
            result['success'] = True
            logger.info(f"✅ Processing complete: {len(quotes)} quotes extracted")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Processing failed: {e}")
        
        return result
    
    def batch_process(
        self,
        files: List[tuple],
        num_quotes_per_file: int = 10
    ) -> List[Dict]:
        """
        Process multiple files in batch
        
        Args:
            files: List of tuples (file_path, file_type, source)
            num_quotes_per_file: Quotes to extract per file
            
        Returns:
            List of processing results
        """
        results = []
        
        logger.info(f"📦 Batch processing {len(files)} files...")
        
        for i, (file_path, file_type, source) in enumerate(files, 1):
            logger.info(f"📄 Processing file {i}/{len(files)}: {Path(file_path).name}")
            
            result = self.process_file(
                file_path=file_path,
                file_type=file_type,
                source=source,
                num_quotes=num_quotes_per_file
            )
            
            results.append(result)
        
        # Summary
        successful = sum(1 for r in results if r['success'])
        total_quotes = sum(len(r['quotes']) for r in results)
        
        logger.info(f"""
✅ Batch processing complete!
   Files processed: {successful}/{len(files)}
   Total quotes extracted: {total_quotes}
        """)
        
        return results


# Example usage and testing functions
def test_single_file():
    """Test processing a single file"""
    processor = ContentProcessor()
    
    # Example: Process a text file
    result = processor.process_file(
        file_path="sample_sermon.txt",
        file_type="text",
        source="Minister Louis Farrakhan",
        num_quotes=5
    )
    
    print(f"Success: {result['success']}")
    print(f"Quotes extracted: {len(result['quotes'])}")
    for quote in result['quotes']:
        print(f"\n- {quote['quote_text']}")
        print(f"  Author: {quote['author']}")
        print(f"  Category: {quote['category']}")


def test_batch_processing():
    """Test batch processing multiple files"""
    processor = ContentProcessor()
    
    # Example: Process multiple files
    files = [
        ("sermon1.mp3", "audio", "Minister Farrakhan"),
        ("lecture2.txt", "text", "Elijah Muhammad"),
        ("speech3.mp4", "video", "Minister Farrakhan"),
    ]
    
    results = processor.batch_process(files, num_quotes_per_file=10)
    
    # Save all quotes to file
    all_quotes = []
    for result in results:
        all_quotes.extend(result['quotes'])
    
    with open('extracted_quotes.json', 'w') as f:
        json.dump(all_quotes, f, indent=2)
    
    print(f"✅ Extracted {len(all_quotes)} total quotes")
    print(f"   Saved to: extracted_quotes.json")


if __name__ == "__main__":
    # Run tests
    print("Testing Content Processor...")
    test_single_file()
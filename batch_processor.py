#!/usr/bin/env python3
"""
Batch Process NOI Content - Command Line Tool
Process entire folders of sermons, lectures, and speeches
"""
import os
import sys
from pathlib import Path
from content_processor import ContentProcessor
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()


def process_folder(folder_path: str, default_source: str = None, num_quotes: int = 10):
    """
    Process all media files in a folder
    
    Args:
        folder_path: Path to folder containing media files
        default_source: Default source attribution
        num_quotes: Quotes to extract per file
    """
    processor = ContentProcessor()
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"❌ Folder not found: {folder_path}")
        return
    
    # Supported extensions
    audio_ext = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
    video_ext = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'}
    text_ext = {'.txt', '.md', '.pdf', '.docx', '.doc'}
    
    # Find all media files
    files = []
    for ext in audio_ext | video_ext | text_ext:
        files.extend(folder.glob(f'*{ext}'))
        files.extend(folder.glob(f'*{ext.upper()}'))
    
    if not files:
        print(f"❌ No media files found in: {folder_path}")
        print(f"   Supported formats: {', '.join(audio_ext | video_ext | text_ext)}")
        return
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  NOI Content Batch Processor                                  ║
╚══════════════════════════════════════════════════════════════╝

📁 Folder: {folder_path}
📄 Files found: {len(files)}
💭 Quotes per file: {num_quotes}
👤 Default source: {default_source or 'Auto-detect'}

Starting batch processing...
""")
    
    # Prepare batch
    batch_files = []
    for file_path in files:
        # Determine file type
        ext = file_path.suffix.lower()
        if ext in audio_ext:
            file_type = 'audio'
        elif ext in video_ext:
            file_type = 'video'
        else:
            file_type = 'text'
        
        # Extract source from filename if not provided
        source = default_source
        if not source:
            # Try to extract from filename (e.g., "farrakhan_sermon.mp3" -> "Farrakhan")
            name = file_path.stem.lower()
            if 'farrakhan' in name:
                source = 'Minister Louis Farrakhan'
            elif 'elijah' in name or 'muhammad' in name:
                source = 'Elijah Muhammad'
        
        batch_files.append((str(file_path), file_type, source))
    
    # Process
    results = processor.batch_process(batch_files, num_quotes_per_file=num_quotes)
    
    # Collect all quotes
    all_quotes = []
    successful = 0
    failed = 0
    
    for result in results:
        if result['success']:
            successful += 1
            all_quotes.extend(result['quotes'])
        else:
            failed += 1
            print(f"❌ Failed: {Path(result['file_path']).name} - {result['error']}")
    
    # Save results
    output_file = folder / f"extracted_quotes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_files': len(files),
            'successful': successful,
            'failed': failed,
            'total_quotes': len(all_quotes),
            'quotes': all_quotes,
            'processed_at': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Batch Processing Complete!                                   ║
╚══════════════════════════════════════════════════════════════╝

✅ Files processed: {successful}/{len(files)}
❌ Files failed: {failed}
💭 Total quotes extracted: {len(all_quotes)}
📝 Results saved to: {output_file.name}

Top quotes by category:
""")
    
    # Show quote breakdown
    categories = {}
    for quote in all_quotes:
        cat = quote.get('category', 'unknown')
        categories[cat] = categories.get(cat, 0) + 1
    
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {category.capitalize()}: {count} quotes")
    
    print(f"\n✨ Ready to use! Import quotes to your database or dashboard.\n")
    
    return output_file


def process_single_file(file_path: str, source: str = None, num_quotes: int = 10):
    """Process a single file"""
    processor = ContentProcessor()
    
    file = Path(file_path)
    if not file.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    # Determine file type
    ext = file.suffix.lower()
    if ext in {'.mp3', '.wav', '.m4a', '.aac', '.ogg'}:
        file_type = 'audio'
    elif ext in {'.mp4', '.mov', '.avi', '.mkv'}:
        file_type = 'video'
    else:
        file_type = 'text'
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Processing Single File                                       ║
╚══════════════════════════════════════════════════════════════╝

📄 File: {file.name}
📁 Type: {file_type}
💭 Quotes to extract: {num_quotes}
👤 Source: {source or 'Auto-detect'}

Processing...
""")
    
    result = processor.process_file(
        file_path=str(file),
        file_type=file_type,
        source=source,
        num_quotes=num_quotes
    )
    
    if result['success']:
        print(f"""
✅ Processing successful!

📝 Transcription: {len(result['transcription'])} characters
💭 Quotes extracted: {len(result['quotes'])}
☁️  S3 Upload: {result['s3_url'] or 'Not configured'}

Extracted quotes:
""")
        for i, quote in enumerate(result['quotes'], 1):
            print(f"\n{i}. \"{quote['quote_text']}\"")
            print(f"   - {quote['author']} ({quote['category']})")
        
        # Save to file
        output_file = file.parent / f"{file.stem}_quotes.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result['quotes'], f, indent=2, ensure_ascii=False)
        
        print(f"\n📝 Saved to: {output_file}")
    else:
        print(f"\n❌ Processing failed: {result['error']}")


def main():
    """Main CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='NOI Content Processor - Extract quotes from sermons, lectures, and speeches',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single file
  python batch_processor.py file sermon.mp3 --source "Minister Farrakhan" --quotes 15
  
  # Process entire folder
  python batch_processor.py folder ~/noi-content/ --source "Minister Farrakhan" --quotes 20
  
  # Process folder without default source (auto-detect from filenames)
  python batch_processor.py folder ~/sermons/ --quotes 10
        """
    )
    
    parser.add_argument(
        'mode',
        choices=['file', 'folder'],
        help='Process a single file or entire folder'
    )
    
    parser.add_argument(
        'path',
        help='Path to file or folder'
    )
    
    parser.add_argument(
        '--source', '-s',
        help='Source attribution (e.g., "Minister Farrakhan")',
        default=None
    )
    
    parser.add_argument(
        '--quotes', '-q',
        type=int,
        default=10,
        help='Number of quotes to extract per file (default: 10)'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'file':
        process_single_file(args.path, args.source, args.quotes)
    else:
        process_folder(args.path, args.source, args.quotes)


if __name__ == '__main__':
    main()
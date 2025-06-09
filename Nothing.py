import logging
import asyncio
import json
import os
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from database.ia_filterdb import Media, Media2
from info import DBX_CHANNEL, OWNERID
import re

logger = logging.getLogger(__name__)

# File to store progress state
PROGRESS_FILE = "sendallfiles_progress.json"

class SendAllFilesManager:
    def __init__(self):
        self.is_running = False
        self.current_db = 1  # 1 for Media, 2 for Media2
        self.current_index = 0
        self.total_files_db1 = 0
        self.total_files_db2 = 0
        self.sent_count = 0
        self.start_time = None
        self.last_progress_log = datetime.now()
        
    async def load_progress(self):
        """Load progress from file if exists"""
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, 'r') as f:
                    data = json.load(f)
                    self.current_db = data.get('current_db', 1)
                    self.current_index = data.get('current_index', 0)
                    self.sent_count = data.get('sent_count', 0)
                    self.total_files_db1 = data.get('total_files_db1', 0)
                    self.total_files_db2 = data.get('total_files_db2', 0)
                    logger.info(f"Progress loaded: DB{self.current_db}, Index: {self.current_index}, Sent: {self.sent_count}")
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
            
    async def save_progress(self):
        """Save current progress to file"""
        try:
            data = {
                'current_db': self.current_db,
                'current_index': self.current_index,
                'sent_count': self.sent_count,
                'total_files_db1': self.total_files_db1,
                'total_files_db2': self.total_files_db2,
                'last_updated': datetime.now().isoformat()
            }
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
            
    async def clear_progress(self):
        """Clear progress file"""
        try:
            if os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)
                logger.info("Progress file cleared")
        except Exception as e:
            logger.error(f"Error clearing progress: {e}")
            
    def get_progress_percentage(self):
        """Calculate current progress percentage"""
        total_files = self.total_files_db1 + self.total_files_db2
        if total_files == 0:
            return 0
        return (self.sent_count / total_files) * 100
        
    async def log_progress(self):
        """Log progress every 30 minutes"""
        current_time = datetime.now()
        if (current_time - self.last_progress_log).total_seconds() >= 1800:  # 30 minutes
            percentage = self.get_progress_percentage()
            logger.info(f"SendAllFiles Progress: {percentage:.2f}% completed ({self.sent_count}/{self.total_files_db1 + self.total_files_db2} files)")
            self.last_progress_log = current_time
            
    async def send_files(self, bot: Client, channel_id: int):
        """Main function to send all files"""
        try:
            self.is_running = True
            self.start_time = datetime.now()
            
            # Load previous progress if exists
            await self.load_progress()
            
            # Get total counts if not loaded from progress
            if self.total_files_db1 == 0 and self.total_files_db2 == 0:
                self.total_files_db1 = await Media.count_documents({})
                self.total_files_db2 = await Media2.count_documents({})
                logger.info(f"Total files - DB1: {self.total_files_db1}, DB2: {self.total_files_db2}")
            
            total_files = self.total_files_db1 + self.total_files_db2
            
            if total_files == 0:
                await bot.send_message(channel_id, "No files found in databases!")
                self.is_running = False
                return
                
            # Start from where we left off
            if self.current_db == 1:
                await self._send_from_db1(bot, channel_id)
                
            if self.current_db <= 2 and self.is_running:
                self.current_db = 2
                self.current_index = max(0, self.current_index - self.total_files_db1) if self.current_index > self.total_files_db1 else 0
                await self._send_from_db2(bot, channel_id)
            
            # Send completion message
            if self.is_running:
                await bot.send_message(channel_id, "Successfully completed 🎊")
                await self.clear_progress()
                logger.info("SendAllFiles process completed successfully!")
                
        except Exception as e:
            logger.error(f"Error in send_files: {e}")
        finally:
            self.is_running = False
            
    async def _send_from_db1(self, bot: Client, channel_id: int):
        """Send files from first database"""
        try:
            cursor = Media.find({}).sort('$natural', 1)  # First to last
            files = await cursor.to_list(length=None)
            
            files_to_process = files[self.current_index:]
            
            for i, file_doc in enumerate(files_to_process):
                if not self.is_running:
                    break
                    
                try:
                    # Create file message
                    file_name = file_doc.file_name
                    file_caption = file_doc.caption or ""
                    
                    # Clean filename for display
                    clean_name = re.sub(r'\(\@\S+\)|\[\@\S+\]|\b@\S+|\bwww\.\S+', '', file_name).strip()
                    
                    # Send file
                    await bot.send_document(
                        chat_id=channel_id,
                        document=file_doc.file_id,
                        caption=f"📁 **{clean_name}**\n\n{file_caption}" if file_caption else f"📁 **{clean_name}**"
                    )
                    
                    self.sent_count += 1
                    self.current_index += 1
                    
                    # Save progress every file
                    await self.save_progress()
                    
                    # Log progress every 30 minutes
                    await self.log_progress()
                    
                    # Sleep after every 30 files
                    if (i + 1) % 30 == 0:
                        logger.info(f"Sent {i + 1} files from DB1, sleeping for 40 seconds...")
                        await asyncio.sleep(40)
                        
                except Exception as e:
                    logger.error(f"Error sending file from DB1: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in _send_from_db1: {e}")
            
    async def _send_from_db2(self, bot: Client, channel_id: int):
        """Send files from second database"""
        try:
            cursor = Media2.find({}).sort('$natural', 1)  # First to last
            files = await cursor.to_list(length=None)
            
            files_to_process = files[self.current_index:]
            
            for i, file_doc in enumerate(files_to_process):
                if not self.is_running:
                    break
                    
                try:
                    # Create file message
                    file_name = file_doc.file_name
                    file_caption = file_doc.caption or ""
                    
                    # Clean filename for display
                    clean_name = re.sub(r'\(\@\S+\)|\[\@\S+\]|\b@\S+|\bwww\.\S+', '', file_name).strip()
                    
                    # Send file
                    await bot.send_document(
                        chat_id=channel_id,
                        document=file_doc.file_id,
                        caption=f"📁 **{clean_name}**\n\n{file_caption}" if file_caption else f"📁 **{clean_name}**"
                    )
                    
                    self.sent_count += 1
                    self.current_index = self.total_files_db1 + (self.current_index - self.total_files_db1 + 1)
                    
                    # Save progress every file
                    await self.save_progress()
                    
                    # Log progress every 30 minutes
                    await self.log_progress()
                    
                    # Sleep after every 30 files
                    if (i + 1) % 30 == 0:
                        logger.info(f"Sent {i + 1} files from DB2, sleeping for 40 seconds...")
                        await asyncio.sleep(40)
                        
                except Exception as e:
                    logger.error(f"Error sending file from DB2: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in _send_from_db2: {e}")

# Create global instance
send_manager = SendAllFilesManager()

@Client.on_message(filters.command("sendallfiles") & filters.chat(DBX_CHANNEL))
async def send_all_files_command(bot: Client, message: Message):
    """Handle /sendallfiles command"""
    try:
        # Check if user is owner
        if message.from_user.id != OWNERID:
            await message.reply("❌ You don't have permission to use this command!")
            return
            
        # Check if process is already running
        if send_manager.is_running:
            percentage = send_manager.get_progress_percentage()
            await message.reply(f"⚠️ SendAllFiles process is already running!\n**Progress:** {percentage:.2f}%")
            return
            
        # Start the process
        await message.reply("🚀 Starting SendAllFiles process...")
        
        # Run in background
        asyncio.create_task(send_manager.send_files(bot, DBX_CHANNEL))
        
    except Exception as e:
        logger.error(f"Error in send_all_files_command: {e}")
        await message.reply(f"❌ Error starting process: {str(e)}")

@Client.on_message(filters.command("stopallfiles") & filters.chat(DBX_CHANNEL))
async def stop_all_files_command(bot: Client, message: Message):
    """Handle /stopallfiles command to stop the process"""
    try:
        # Check if user is owner
        if message.from_user.id != OWNERID:
            await message.reply("❌ You don't have permission to use this command!")
            return
            
        if not send_manager.is_running:
            await message.reply("⚠️ No SendAllFiles process is currently running!")
            return
            
        send_manager.is_running = False
        percentage = send_manager.get_progress_percentage()
        await message.reply(f"🛑 SendAllFiles process stopped!\n**Progress saved:** {percentage:.2f}%\n\nUse /sendallfiles to resume from where it stopped.")
        
    except Exception as e:
        logger.error(f"Error in stop_all_files_command: {e}")
        await message.reply(f"❌ Error stopping process: {str(e)}")

@Client.on_message(filters.command("statusallfiles") & filters.chat(DBX_CHANNEL))
async def status_all_files_command(bot: Client, message: Message):
    """Handle /statusallfiles command to check progress"""
    try:
        # Check if user is owner
        if message.from_user.id != OWNERID:
            await message.reply("❌ You don't have permission to use this command!")
            return
            
        if send_manager.is_running:
            percentage = send_manager.get_progress_percentage()
            total_files = send_manager.total_files_db1 + send_manager.total_files_db2
            current_db_text = "Database 1 (Media)" if send_manager.current_db == 1 else "Database 2 (Media2)"
            
            status_text = f"""📊 **SendAllFiles Status**
            
🔄 **Status:** Running
📊 **Progress:** {percentage:.2f}%
📁 **Files Sent:** {send_manager.sent_count}/{total_files}
🗄️ **Current DB:** {current_db_text}
📍 **Current Index:** {send_manager.current_index}

**Database Info:**
• DB1 Files: {send_manager.total_files_db1}
• DB2 Files: {send_manager.total_files_db2}
• Total Files: {total_files}
            """
        else:
            # Load progress to show last status
            await send_manager.load_progress()
            if send_manager.sent_count > 0:
                percentage = send_manager.get_progress_percentage()
                total_files = send_manager.total_files_db1 + send_manager.total_files_db2
                status_text = f"""📊 **SendAllFiles Status**
                
⏸️ **Status:** Stopped
📊 **Last Progress:** {percentage:.2f}%
📁 **Files Sent:** {send_manager.sent_count}/{total_files}

Use /sendallfiles to resume the process.
                """
            else:
                status_text = "📊 **SendAllFiles Status**\n\n⏹️ **Status:** Not started\n\nUse /sendallfiles to start the process."
                
        await message.reply(status_text)
        
    except Exception as e:
        logger.error(f"Error in status_all_files_command: {e}")
        await message.reply(f"❌ Error getting status: {str(e)}")

# Auto-resume on bot restart
async def auto_resume_sendallfiles(bot: Client):
    """Auto-resume sendallfiles process on bot restart if it was running"""
    try:
        if os.path.exists(PROGRESS_FILE):
            await send_manager.load_progress()
            if send_manager.sent_count > 0:
                total_files = send_manager.total_files_db1 + send_manager.total_files_db2
                if send_manager.sent_count < total_files:
                    logger.info(f"Auto-resuming SendAllFiles process from {send_manager.get_progress_percentage():.2f}%")
                    await bot.send_message(DBX_CHANNEL, f"🔄 Auto-resuming SendAllFiles process...\n**Progress:** {send_manager.get_progress_percentage():.2f}%")
                    asyncio.create_task(send_manager.send_files(bot, DBX_CHANNEL))
    except Exception as e:
        logger.error(f"Error in auto_resume_sendallfiles: {e}")

# Call this function when bot starts
# Add this to your main bot startup code:
# asyncio.create_task(auto_resume_sendallfiles(bot))

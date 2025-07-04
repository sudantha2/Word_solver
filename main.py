import logging
import re
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load 5-letter words from file
def load_words():
    words = []
    try:
        with open('words.txt', 'r') as f:
            for line in f:
                word = line.strip().lower()
                if len(word) == 5 and word.isalpha():
                    words.append(word)
    except FileNotFoundError:
        logger.error("words.txt file not found!")
        return []
    return words

WORD_LIST = load_words()
logger.info(f"Loaded {len(WORD_LIST)} 5-letter words")

# Store user sessions
user_sessions = defaultdict(list)

def parse_guess(message):
    """Parse a guess message like '🟨 🟩 🟥 🟥 🟨 **LAMAR**' or 'GUESS 🟥🟨🟩🟥🟥' or '🟨 🟩 🟥 🟥 🟨 𝗟𝗔𝗠𝗔𝗥'"""
    
    # Mathematical Sans-Serif Bold Capital Letters mapping
    math_bold_to_regular = {
        '𝗔': 'A', '𝗕': 'B', '𝗖': 'C', '𝗗': 'D', '𝗘': 'E', '𝗙': 'F', '𝗚': 'G', '𝗛': 'H',
        '𝗜': 'I', '𝗝': 'J', '𝗞': 'K', '𝗟': 'L', '𝗠': 'M', '𝗡': 'N', '𝗢': 'O', '𝗣': 'P',
        '𝗤': 'Q', '𝗥': 'R', '𝗦': 'S', '𝗧': 'T', '𝗨': 'U', '𝗩': 'V', '𝗪': 'W', '𝗫': 'X',
        '𝗬': 'Y', '𝗭': 'Z'
    }
    
    def convert_math_bold_to_regular(text):
        """Convert Mathematical Sans-Serif Bold letters to regular letters"""
        result = ''
        for char in text:
            result += math_bold_to_regular.get(char, char)
        return result
    
    # Pattern for Mathematical Sans-Serif Bold format: emojis with spaces first, then math bold word
    pattern_math_bold = r'([🟥🟨🟩]\s*){5}\s*([𝗔-𝗭]{5})'
    match_math_bold = re.search(pattern_math_bold, message)
    
    if match_math_bold:
        # Extract emojis and remove spaces
        emoji_part = message.split(match_math_bold.group(2))[0].strip()
        emoji_result = re.sub(r'\s+', '', emoji_part)
        math_bold_word = match_math_bold.group(2)
        guess_word = convert_math_bold_to_regular(math_bold_word).lower()
        return guess_word, emoji_result
    
    # New format: emojis with spaces first, then bold word
    pattern1 = r'([🟥🟨🟩]\s*){5}\s*\*\*([a-zA-Z]{5})\*\*'
    match1 = re.search(pattern1, message)
    
    if match1:
        # Extract emojis and remove spaces
        emoji_part = message.split('**')[0].strip()
        emoji_result = re.sub(r'\s+', '', emoji_part)
        guess_word = match1.group(2).lower()
        return guess_word, emoji_result
    
    # Old format: word followed by emoji squares
    pattern2 = r'([a-zA-Z]{5})\s*([🟥🟨🟩]{5})'
    match2 = re.search(pattern2, message)
    
    if match2:
        guess_word = match2.group(1).lower()
        emoji_result = match2.group(2)
        return guess_word, emoji_result
    
    return None, None

def parse_multiple_guesses(message):
    """Parse multiple guesses from a message"""
    guesses = []
    lines = message.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        guess_word, emoji_result = parse_guess(line)
        if guess_word and emoji_result:
            guesses.append((guess_word, emoji_result))
    
    return guesses

def filter_words_by_clues(words, clues):
    """Filter words based on all collected clues"""
    valid_words = []
    
    for word in words:
        is_valid = True
        
        for guess_word, emoji_result in clues:
            # Check each position
            for i, (guess_char, emoji) in enumerate(zip(guess_word, emoji_result)):
                if emoji == '🟩':  # Green - correct letter, correct position
                    if word[i] != guess_char:
                        is_valid = False
                        break
                elif emoji == '🟨':  # Yellow - correct letter, wrong position
                    if guess_char not in word or word[i] == guess_char:
                        is_valid = False
                        break
                elif emoji == '🟥':  # Red - letter not in word
                    if guess_char in word:
                        is_valid = False
                        break
            
            if not is_valid:
                break
        
        if is_valid:
            valid_words.append(word)
    
    return valid_words

def get_letter_frequency(words):
    """Get frequency of letters in remaining words to suggest best guess"""
    freq = defaultdict(int)
    for word in words:
        for char in set(word):  # Use set to count each letter once per word
            freq[char] += 1
    return freq

def score_word(word, letter_freq):
    """Score a word based on letter frequency"""
    score = 0
    used_letters = set()
    for char in word:
        if char not in used_letters:
            score += letter_freq[char]
            used_letters.add(char)
    return score

def word_matches_clue(word, guess_word, emoji_result):
    """Check if a word matches a single guess clue"""
    for i, (guess_char, emoji) in enumerate(zip(guess_word, emoji_result)):
        if emoji == '🟩':  # Green - correct letter, correct position
            if word[i] != guess_char:
                return False
        elif emoji == '🟨':  # Yellow - correct letter, wrong position
            if guess_char not in word or word[i] == guess_char:
                return False
        elif emoji == '🟥':  # Red - letter not in word
            if guess_char in word:
                return False
    return True

def get_best_guess(words):
    """Get the best next guess from remaining words"""
    if not words:
        return None
    
    if len(words) == 1:
        return words[0]
    
    # Calculate letter frequencies
    letter_freq = get_letter_frequency(words)
    
    # Score all words and return the best one
    best_word = max(words, key=lambda w: score_word(w, letter_freq))
    return best_word

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    user_id = update.effective_user.id
    user_sessions[user_id] = []
    
    welcome_message = (
        "🎯 Welcome to Wordle Solver Bot!\n\n"
        "Send me your guesses in any of these formats:\n"
        "• 🟨 🟩 🟥 🟥 🟨 **LAMAR**\n"
        "• 🟨 🟩 🟥 🟥 🟨 𝗟𝗔𝗠𝗔𝗥\n"
        "• GUESS 🟥🟨🟩🟥🟥\n\n"
        "You can also send multiple guesses at once (one per line):\n"
        "🟨 🟥 🟥 🟥 🟥 𝗙𝗔𝗜𝗥𝗬\n"
        "🟥 🟨 🟥 🟥 🟩 𝗖𝗟𝗜𝗙𝗙\n\n"
        "Where:\n"
        "🟩 = Correct letter, correct position\n"
        "🟨 = Correct letter, wrong position\n"
        "🟥 = Letter not in the word\n\n"
        "Commands:\n"
        "• /reset - Clear your session\n"
        "• /other - Get alternative word suggestions\n\n"
        f"I know {len(WORD_LIST)} 5-letter words!"
    )
    
    await update.message.reply_text(welcome_message)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset command handler"""
    user_id = update.effective_user.id
    user_sessions[user_id] = []
    await update.message.reply_text("🔄 Session reset! Send me your first guess.")

async def other_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide alternative word suggestions"""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions or not user_sessions[user_id]:
        await update.message.reply_text(
            "❌ No guesses recorded yet! Send me your first guess to get started."
        )
        return
    
    # Filter words based on current clues
    remaining_words = filter_words_by_clues(WORD_LIST, user_sessions[user_id])
    
    if not remaining_words:
        # No exact matches, but provide helpful alternatives
        response_parts = ["🚫 **No words match all clues perfectly!**", ""]
        
        # Find words that match the most clues
        word_scores = {}
        for word in WORD_LIST:
            matches = 0
            for guess_word, emoji_result in user_sessions[user_id]:
                if word_matches_clue(word, guess_word, emoji_result):
                    matches += 1
            if matches > 0:
                word_scores[word] = matches
        
        if word_scores:
            # Sort by number of matching clues
            sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
            max_matches = sorted_words[0][1]
            
            response_parts.append(f"🔍 **Best partial matches** (matching {max_matches}/{len(user_sessions[user_id])} clues):")
            
            # Group by number of matches
            current_matches = max_matches
            words_with_current_matches = [word for word, matches in sorted_words if matches == current_matches]
            
            # Get letter frequency for scoring within the group
            letter_freq = get_letter_frequency(words_with_current_matches)
            scored_words = [(word, score_word(word, letter_freq)) for word in words_with_current_matches]
            scored_words.sort(key=lambda x: x[1], reverse=True)
            
            top_words = [f"`{word.upper()}`" for word, _ in scored_words[:8]]
            response_parts.append(f"🥇 **Top picks:** {', '.join(top_words[:3])}")
            if len(top_words) > 3:
                response_parts.append(f"🥈 **Good options:** {', '.join(top_words[3:6])}")
            if len(top_words) > 6:
                response_parts.append(f"🥉 **Other choices:** {', '.join(top_words[6:8])}")
        
        # Suggest some high-frequency common words
        common_words = ['about', 'other', 'which', 'their', 'would', 'there', 'could', 'still', 'after', 'being']
        available_common = [word for word in common_words if word in WORD_LIST]
        if available_common:
            response_parts.append("")
            response_parts.append("💡 **Try common words:**")
            common_formatted = [f"`{word.upper()}`" for word in available_common[:5]]
            response_parts.append(f"   {', '.join(common_formatted)}")
        
        response_parts.append("")
        response_parts.append("🔄 Use /reset to start over")
        
        response = "\n".join(response_parts)
        await update.message.reply_text(response, parse_mode='Markdown')
        return
    
    if len(remaining_words) == 1:
        await update.message.reply_text(
            f"🎯 Only one word matches your clues: `{remaining_words[0].upper()}`"
        )
        return
    
    # Get letter frequencies for scoring
    letter_freq = get_letter_frequency(remaining_words)
    
    # Score all words and get top alternatives
    scored_words = [(word, score_word(word, letter_freq)) for word in remaining_words]
    scored_words.sort(key=lambda x: x[1], reverse=True)
    
    # Get top 8 alternatives
    top_words = [f"`{word.upper()}`" for word, _ in scored_words[:8]]
    
    response_parts = [
        f"🎲 **Alternative suggestions** ({len(remaining_words)} possible words):",
        "",
        f"🥇 **Top picks:** {', '.join(top_words[:3])}",
        f"🥈 **Good options:** {', '.join(top_words[3:6])}",
        f"🥉 **Other choices:** {', '.join(top_words[6:8])}"
    ]
    
    if len(remaining_words) <= 15:
        all_words = [f"`{w.upper()}`" for w in remaining_words]
        response_parts.append(f"\n📝 **All possibilities:** {', '.join(all_words)}")
    
    response = "\n".join(response_parts)
    await update.message.reply_text(response, parse_mode='Markdown')

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle guess messages"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Try to parse multiple guesses first
    guesses = parse_multiple_guesses(message_text)
    
    if not guesses:
        # Fall back to single guess parsing
        guess_word, emoji_result = parse_guess(message_text)
        
        if not guess_word or not emoji_result:
            await update.message.reply_text(
                "❌ Invalid format! Please use any of these:\n"
                "• 🟨 🟩 🟥 🟥 🟨 **LAMAR**\n"
                "• 🟨 🟩 🟥 🟥 🟨 𝗟𝗔𝗠𝗔𝗥\n"
                "• GUESS 🟥🟨🟩🟥🟥\n\n"
                "Or send multiple guesses, one per line.\n"
                "Make sure you have exactly 5 letters and 5 emoji squares.\n\n"
                "Use /reset to start over or /other for suggestions."
            )
            return
        
        guesses = [(guess_word, emoji_result)]
    
    # Add all guesses to user session
    for guess_word, emoji_result in guesses:
        user_sessions[user_id].append((guess_word, emoji_result))
    
    # Filter words based on all clues
    remaining_words = filter_words_by_clues(WORD_LIST, user_sessions[user_id])
    
    if not remaining_words:
        # Analyze each guess individually to provide helpful feedback
        response_parts = ["🚫 **No words match all your clues!**", ""]
        
        # Show analysis of each guess
        response_parts.append("📊 **Clue Analysis:**")
        for i, (guess_word, emoji_result) in enumerate(user_sessions[user_id], 1):
            response_parts.append(f"  {i}. `{guess_word.upper()}` {emoji_result}")
        
        # Try to find words that match most clues
        best_matches = []
        max_matches = 0
        
        for word in WORD_LIST:
            matches = 0
            for guess_word, emoji_result in user_sessions[user_id]:
                if word_matches_clue(word, guess_word, emoji_result):
                    matches += 1
            
            if matches > max_matches:
                max_matches = matches
                best_matches = [word]
            elif matches == max_matches and matches > 0:
                best_matches.append(word)
        
        if best_matches and max_matches > 0:
            response_parts.append("")
            response_parts.append(f"🔍 **Words matching {max_matches}/{len(user_sessions[user_id])} clues:**")
            top_matches = [f"`{w.upper()}`" for w in best_matches[:15]]
            response_parts.append(f"   {', '.join(top_matches)}")
            if len(best_matches) > 15:
                response_parts.append(f"   ...and {len(best_matches) - 15} more")
        
        # Suggest most common letters from all guesses
        all_letters = set()
        for guess_word, emoji_result in user_sessions[user_id]:
            for i, (letter, emoji) in enumerate(zip(guess_word, emoji_result)):
                if emoji == '🟩':  # Green letters are confirmed
                    all_letters.add(letter)
                elif emoji == '🟨':  # Yellow letters are in the word
                    all_letters.add(letter)
        
        if all_letters:
            # Find words containing these confirmed letters
            suggested_words = []
            for word in WORD_LIST:
                if any(letter in word for letter in all_letters):
                    suggested_words.append(word)
            
            if suggested_words:
                # Score by letter frequency
                letter_freq = get_letter_frequency(suggested_words)
                scored_words = [(word, score_word(word, letter_freq)) for word in suggested_words]
                scored_words.sort(key=lambda x: x[1], reverse=True)
                
                response_parts.append("")
                response_parts.append("💡 **Suggested words with confirmed letters:**")
                top_suggestions = [f"`{word.upper()}`" for word, _ in scored_words[:10]]
                response_parts.append(f"   {', '.join(top_suggestions)}")
        
        response_parts.append("")
        response_parts.append("🔄 Use /reset to start over • /other for more suggestions")
        
        response = "\n".join(response_parts)
        await update.message.reply_text(response, parse_mode='Markdown')
        return
    
    # Get best guess
    best_guess = get_best_guess(remaining_words)
    
    # Create response with analysis
    response_parts = []
    
    if len(guesses) > 1:
        response_parts.append(f"📝 Processed {len(guesses)} guesses")
    
    if len(remaining_words) == 1:
        response_parts.append(f"🎉 Found it! The word is: `{best_guess.upper()}`")
        response_parts.append("\n🔄 Use /reset to start a new game!")
    else:
        response_parts.append(f"💡 Best next guess: `{best_guess.upper()}`")
        response_parts.append(f"📊 {len(remaining_words)} possible words remaining")
        
        # Show some examples if there are few remaining words
        if len(remaining_words) <= 10:
            other_words = [f"`{w.upper()}`" for w in remaining_words if w != best_guess][:5]
            if other_words:
                response_parts.append(f"🔍 Other possibilities: {', '.join(other_words)}")
        
        response_parts.append("\n🎲 Use /other for more suggestions • /reset to start over")
    
    response = "\n".join(response_parts)
    await update.message.reply_text(response, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.warning(f'Update {update} caused error {context.error}')

def main() -> None:
    """Start the bot"""
    TOKEN = '7695188163:AAFLPNDuxRIJkEkUMpG_Qijfi7-OoILOMzM'
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("other", other_suggestions))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_guess
    ))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Starting Wordle Solver Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    if not WORD_LIST:
        print("Error: Could not load words from words.txt")
        exit(1)
    main()

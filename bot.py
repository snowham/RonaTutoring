import discord, sqlite3, asyncio, db_funcs
from discord.ext import commands, tasks

# Initialize bot
intents = discord.Intents(messages=True, guilds=True, reactions=True, members=True, presences=True)
client = commands.Bot(command_prefix='rona ', intents=intents)

# Open database
conn = sqlite3.connect("ronatutoring.sqlite")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Constants
tellTutorToReact = '''
            
React to this message with an emoji of your choice if you're interested in taking this request. Our discord bot will reach out to those interested with more details.'''

# Send tutor requests to tutor-request channel every 2 hours
async def send_requests():
    await client.wait_until_ready()
    while True:
        # Delete all requests
        while True:
            deleted = await client.get_guild(671509704157167646).get_channel(787592274119884843).purge(limit=100)
            if len(deleted) == 0:
                break

        # From pending_requests database, get discordMessage
        cur.execute("SELECT * FROM pending_requests")
        rows = cur.fetchall()
        discordMessages = [row['discordMessage'] for row in rows]
        for message in discordMessages:
            # Send pending request message
            await client.get_guild(671509704157167646).get_channel(787592274119884843).send(f"{client.get_guild(671509704157167646).default_role} {message}")

        # Wait 2 hours for reactions from tutors
        await asyncio.sleep(30)

        cur.execute("SELECT * FROM confirmation_message_counters")
        counters = cur.fetchall()
        tutorIds = [counter['tutorId'] for counter in counters]
        # Go through all pending requests from this 2 hour period
        async for message in client.get_guild(671509704157167646).get_channel(787592274119884843).history():
            if len(message.reactions) >= 1:
                # Send confirmation messages to all people who reacted
                # Some people might have reacted twice or more with different emojis; we want to send a confirmation message to them only ONCE
                ids = []
                for reaction in message.reactions:
                    async for user in reaction.users():
                        if user.id not in ids:
                            # Make sure the tutor only gets a confirmation given a specific discordMessage ONCE
                            cur.execute('SELECT * FROM pending_confirmations WHERE tutorId = ? AND discordMessage = ?', (user.id, message.content))
                            alreadyInPendingConfirmations = len(cur.fetchall()) == 1
                            cur.execute('SELECT * FROM tutor_student_tracker WHERE discordMessage = ?', (message.content,))
                            alreadyInTutorStudentTracker = len(cur.fetchall()) >= 1
                            if alreadyInPendingConfirmations or alreadyInTutorStudentTracker:
                                continue

                            # If this is the first time a tutor reacted to a request, initialize the confirmationMessageCount to 1 in the confirmation_message_counters table
                            if user.id not in tutorIds:
                                newConfirmationMessageCount = 1
                                cur.execute('INSERT INTO confirmation_message_counters (tutorId, confirmationMessageCount) VALUES (?, ?)', (user.id, newConfirmationMessageCount))
                            # If this is not the first time a tutor reacted to a request, increment the confirmationMessageCount by 1 in the confirmation_message_counters table
                            else:
                                newConfirmationMessageCount = list(filter(lambda counter: counter['tutorId']==user.id, counters))[0]['confirmationMessageCount'] + 1
                                cur.execute('UPDATE confirmation_message_counters SET confirmationMessageCount = ? WHERE tutorId = ?', (newConfirmationMessageCount, user.id))

                            # Send confirmation message
                            # message.content[:(-1)*len(tellTutorToReact)] ==> the tutor-requests message, without the "React to this message..." part
                            await user.send(f"{message.content[:(-1)*len(tellTutorToReact)]}\n\nAre you sure you want this student? Text either \"yes {newConfirmationMessageCount}\" or \"no {newConfirmationMessageCount}\" (all undercase, without the quotes)")

                            # Add to pending_confirmations table in database
                            cur.execute('INSERT INTO pending_confirmations (tutorId, confirmationMessageIndex, discordMessage) VALUES (?, ?, ?)', (user.id, newConfirmationMessageCount, message.content))
                            conn.commit()
                        ids.append(user.id)
                ids.clear()


# Before doing anything *important* wait for bot to be ready
@client.event
async def on_ready():
    print("Bot is ready.")

@client.listen('on_message')
async def confirmation(message):
    # If message is in DM, is possibly a reply to a confirmation message, and is not from the bot itself (bot's id is 785976319489998898), then continue, else return
    if not (isinstance(message.channel, discord.DMChannel) and (message.content.startswith('yes ') or message.content.startswith('no ')) and (message.author.id != 785976319489998898)):
        return

    # Extract the "yes " or "no " and try to get the confirmationMessageIndex, if doesn't work return
    if message.content.startswith('yes '):
        confirm = True
        confirmationMessageIndex = message.content[4:]
    elif message.content.startswith('no '):
        confirm = False
        confirmationMessageIndex = message.content[3:]
    try:
        confirmationMessageIndex = int(confirmationMessageIndex)
    except:
        return
    
    # Collect current database information
    cur.execute('SELECT * FROM pending_confirmations WHERE tutorId = ? AND confirmationMessageIndex = ?', (message.author.id, confirmationMessageIndex))
    pending_confirmation = cur.fetchall()
    cur.execute('SELECT * FROM tutor_student_tracker WHERE tutorId = ? AND confirmationMessageIndex = ?', (message.author.id, confirmationMessageIndex))
    currentPair = cur.fetchall()

    # Make sure the indexes are valid
    if len(pending_confirmation) == 1:
        discordMessage = pending_confirmation[0]['discordMessage']
    elif len(currentPair) == 1:
        discordMessage = currentPair[0]['discordMessage']
    else:
        return
    
    cur.execute('SELECT * FROM tutor_student_tracker WHERE discordMessage = ?', (discordMessage,))
    allPairs = cur.fetchall()
    
    # Send messages and manage database

    # If they said yes:
    if confirm:
        # If the tutor already has the student
        if len(currentPair) == 1:
            # Tell them
            await message.channel.send('You already have this student.')

        # If someone else is already tutoring the student
        elif len(allPairs) >= 1 and len(currentPair) == 0:
            # Tell them
            await message.channel.send('Unfortunately, someone is already tutoring this student. Hopefully you find another student!')
            # Remove the tutor's pending confirmation from the table
            db_funcs.removePendingConfirmation(conn, cur, message.author.id, confirmationMessageIndex)

        # Only case where they are added to tutor student tracker
        elif len(pending_confirmation) == 1 and len(allPairs) == 0:
            # Add to the tutor student tracker
            db_funcs.addTutorStudentPair(conn, cur, message.author.id, confirmationMessageIndex, discordMessage)
            # Get student information and send to tutor so they can contact the student
            cur.execute('SELECT * FROM tutor_student_tracker WHERE tutorId = ? AND confirmationMessageIndex = ? AND discordMessage = ?', (message.author.id, confirmationMessageIndex, discordMessage))
            newPair = cur.fetchall()[0]
            subjects = f"{'Math, ' if newPair['math'] else ''}{'Science, ' if newPair['science'] else ''}{'English, ' if newPair['english'] else ''}{'History, ' if newPair['history'] else ''}{'Computer Science, ' if newPair['compsci'] else ''}{newPair['otherSubj'] if newPair['otherSubj'] else ''}".strip()
            if subjects[-1] == ',': subjects = subjects[:-1]
            student_info = f'''Great! Here's the student's information:
Parent's Name: **{newPair['parentFullName']}**
Student's Name: **{newPair['studentFullName']}**
Age: **{newPair['age']}**
Grade: **{newPair['grade']}**
Available: **{newPair['availability']}**
Parent's Email: **{newPair['parentContact']}**
Student's Email: **{newPair['studentContact']}**
To Be Tutored In: **{subjects}**
Specific Classes: **{newPair['specificClass']}**
Here is the email format so you can reach out to the student to start tutoring sessions
https://docs.google.com/document/d/1Ooo0VTK1_YbEP9EgCfzg7kgqINXXkns70a5M3UWP32w/edit?usp=sharing
If you have any questions or there's anything wrong, please ask someone from the Operations Team in the Rona Tutoring Server'''
            await message.channel.send(student_info)    

    # If they said no:
    else:
        # If the tutor has the student
        if len(currentPair) == 1:
            # Tell them
            await message.channel.send('You still have this student. If you would like to stop tutoring the student, please inform someone from Operations in the Rona Tutoring Server.')
        # If the tutor doesn't have the student
        elif len(currentPair) == 0:
            # Reply
            await message.channel.send('Alright, thanks for letting us know!')
            # Remove the tutor's pending confirmation from the table
            db_funcs.removePendingConfirmation(conn, cur, message.author.id, confirmationMessageIndex)



# Welcome new users
@client.event
async def on_member_join(member):
    print(f'{member} has joined this server.')
    for channel in member.guild.channels:
        if str(channel) == "welcome":
            await channel.send(f"Hi {member.mention}! Welcome!")

# Track when users leave server
@client.event
async def on_member_remove(member):
    print(f'{member} has left this server.')

# When a tutor doesn't want to continue with Rona Tutoring, someone can run this in the staff-commands channel
@client.command()
async def deleteTutor(ctx, *, tutorId):
    # Make sure message is in staff-commands channel
    if str(ctx.channel) != 'staff-commands':
        await ctx.send("You can only use this command in the staff-commands channel.")
        return
    # Try to delete tutor from database
    try:
        tutorId = int(tutorId)
        if db_funcs.deleteTutor(conn, cur, tutorId):
            await ctx.send("This tutor's information has been deleted from the database.")
        else:
            await ctx.send("The number/id you inputted does not exist in the database.")
    # If doesn't work, report back
    except:
        await ctx.send("Something went wrong. Please make sure you format your command as \"rona deleteTutor <tutor id>\"")

# When a tutor can't tutor a specific student or vice versa, someone can run this in the staff-commands channel
# Inputs tutorId, parentContact, and studentFullName
@client.command()
async def deletePair(ctx, *, inpt):
    # Make sure message is in staff-commands channel
    if str(ctx.channel) != 'staff-commands':
        await ctx.send("You can only use this command in the staff-commands channel.")
        return
    # Try to delete tutor student pair
    try:
        inpt = inpt.strip()
        tutorId = inpt[:inpt.find(' ')]
        tutorId = int(tutorId)
        inpt = inpt[inpt.find(' ')+1:]
        parentContact = inpt[:inpt.find(' ')]
        studentFullName = inpt[inpt.find(' ')+1:]
        if db_funcs.deletePair(conn, cur, tutorId, parentContact, studentFullName):
            await ctx.send("This tutor student pair has been deleted from the tutor student tracker in the database.")
        else:
            await ctx.send("The number/id, parent contact, and/or student full name you inputted do(es) not exist in the database.")
    # If doesn't work, report back
    except:
        await ctx.send("Something went wrong. Please make sure you format your command as \"rona deletePair <tutor id> <parent contact> <student full name>\"")

# Run bot
client.loop.create_task(send_requests())
client.run('Nzg1OTc2MzE5NDg5OTk4ODk4.X8_rfQ.IUzfWED5sfvfNbMkjybDfA2863c')

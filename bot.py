import discord, sqlite3, asyncio, db_funcs, os
from discord.ext import commands, tasks

# Initialize bot
intents = discord.Intents(messages=True, guilds=True, reactions=True, members=True, presences=True)
client = commands.Bot(command_prefix='rona ', intents=intents)

# Open database
conn = sqlite3.connect("ronatutoring.sqlite")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Constants
discord_token = os.environ.get("DISCORD_TOKEN")
server_id = 704196952308318250
tutor_requests_id = 705982389234696284
bot_id = 785976319489998898
tellTutorToReact = '''
            
React to this message with an emoji of your choice if you're interested in taking this request. Our discord bot will reach out to those interested with more details.'''


# Send tutor requests to tutor-request channel every 2 hours
async def send_requests():
    await client.wait_until_ready()
    while True:
        # Delete all requests
        deleted = [1]
        while True:
            deleted = await client.get_guild(server_id).get_channel(tutor_requests_id).purge()
            if len(deleted) == 0:
                break

        # From pending_requests database, get discordMessage
        cur.execute("SELECT * FROM pending_requests")
        rows = cur.fetchall()
        discordMessages = [row['discordMessage'] for row in rows]
        for message in discordMessages:
            # Send pending request message
            await client.get_guild(server_id).get_channel(tutor_requests_id).send(f"{client.get_guild(server_id).default_role} {message}")

        # Wait 1 day for reactions from tutors
        await asyncio.sleep(86400)

        # Go through all pending requests from this 2 hour period
        async for message in client.get_guild(server_id).get_channel(tutor_requests_id).history():
            if len(message.reactions) >= 1:
                # Get all the tutor ids from the confirmation_message_counters table
                cur.execute("SELECT * FROM confirmation_message_counters")
                counters = cur.fetchall()
                tutorIds = [counter['tutorId'] for counter in counters]

                # Send confirmation messages to all people who reacted
                # Some people might have reacted twice or more with different emojis; we want to send a confirmation message to them only ONCE
                ids = []
                for reaction in message.reactions:
                    async for user in reaction.users():
                        if user.id not in ids:
                            # Make sure the tutor only gets a confirmation given a specific discordMessage ONCE
                            cur.execute('SELECT * FROM pending_confirmations WHERE tutorId = ? AND discordMessage = ?', (user.id, message.content))
                            alreadyInPendingConfirmations = len(cur.fetchall()) == 1
                            if alreadyInPendingConfirmations:
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
    # If message is in DM, is possibly a reply to a confirmation message, and is not from the bot itself, then continue, else return
    if not (isinstance(message.channel, discord.DMChannel) and (message.content.startswith('yes ') or message.content.startswith('no ')) and (message.author.id != bot_id)):
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
If you have any issues with your student, please send someone on the Operations team a screenshot of this message with the caption "{newPair['parentContact']} {newPair['studentFullName']}". 
If you have any questions or there's anything wrong, please ask someone from the Operations Team in the Rona Tutoring Server.'''
            await message.channel.send(student_info)    

    # If they said no:
    else:
        # If the tutor has the student
        if len(currentPair) == 1:
            # Tell them
            await message.channel.send('You still have this student. If you would like to stop tutoring the student, use the command: "rona stopTutoring <parent email> <student full name>". If that doesn\'t work, please inform someone from the Operations Team in the Rona Tutoring Server.')
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
        if str(channel) == "random":
            await channel.send(f"Hi {member.mention}, welcome to the Rona Tutoring Server!!")

# Track when users leave server
@client.event
async def on_member_remove(member):
    print(f'{member} has left this server.')

# When a tutor doesn't want to continue with Rona Tutoring, SOMEONE ELSE can run this in the staff-commands channel
@client.command()
async def deleteTutor(ctx, *, tutorId=None):
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

# Deletes tutor-student pair from database. Student DOES NOT go back to pending requests
# Inputs tutorId, parentContact, and studentFullName
@client.command()
async def deletePair(ctx, *, inpt=None):
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
            await ctx.send("The number/id, parent email, and/or student full name you inputted do(es) not exist in the database.")
    # If doesn't work, report back
    except:
        await ctx.send("Something went wrong. Please make sure you format your command as \"rona deletePair <tutor id> <parent email> <student full name>\"")

# Deletes tutor-student pair from database. Student DOES go back to pending requests
# Inputs tutorId, parentContact, and studentFullName
@client.command()
async def reassignStudent(ctx, *, inpt=None):
    # Make sure message is in staff-commands channel
    if str(ctx.channel) != 'staff-commands':
        await ctx.send("You can only use this command in the staff-commands channel.")
        return
    # Try to reassign student
    try:
        inpt = inpt.strip()
        tutorId = inpt[:inpt.find(' ')]
        tutorId = int(tutorId)
        inpt = inpt[inpt.find(' ')+1:]
        parentContact = inpt[:inpt.find(' ')]
        studentFullName = inpt[inpt.find(' ')+1:]
        if db_funcs.reassignStudent(conn, cur, tutorId, parentContact, studentFullName):
            await ctx.send("This tutor student pair has been deleted from the tutor student tracker in the database, and the student has been readded to the pending requests.")
        else:
            await ctx.send("The number/id, parent email, and/or student full name you inputted do(es) not exist in the database.")
    # If doesn't work, report back
    except:
        await ctx.send("Something went wrong. Please make sure you format your command as \"rona reassignStudent <tutor id> <parent email> <student full name>\"")

'''
# When a tutor can't tutor a specific student or vice versa, THEY can run this in their DM with the bot
# Inputs parentContact and studentFullName
@client.command()
async def stopTutoring(ctx, *, inpt=None):
    # Make sure message is in DM channel
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("You can only use this command in a DM with the Rona Tutoring Bot.")
        return
    # Try to delete tutor student pair
    try:
        inpt = inpt.strip()
        parentContact = inpt[:inpt.find(' ')]
        studentFullName = inpt[inpt.find(' ')+1:]
        if db_funcs.deletePair(conn, cur, ctx.author.id, parentContact, studentFullName):
            await ctx.send("You now don't have to tutor this student anymore. If you want to tutor someone else, you can go to the tutor-requests channel in the Rona Tutoring Server and react to a student that you would like to tutor.")
        else:
            await ctx.send("Something went wrong. Please make sure you format your command as \"rona stopTutoring <parent email> <student full name>\", and make sure the student's parent email and full name are correct. \nYou'll get the parent email and student full name from the message that this bot sent you with all of the student's information.")
    # If doesn't work, report back
    except:
        await ctx.send("Something went wrong. Please make sure you format your command as \"rona stopTutoring <parent email> <student full name>\", and make sure the student's parent email and full name are correct. \nYou'll get the parent email and student full name from the message that this bot sent you with all of the student's information.")
'''

# Run bot
client.loop.create_task(send_requests())
client.run(discord_token)

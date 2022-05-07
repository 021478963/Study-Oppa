import discord
import json
import pathlib
import datetime
import asyncio
from discord.ext import commands

async def study(client, member, channel):
  """
  Lists the sections available to review, if there is at least one nonempty 
  section in the user's directory. Otherwise, state that there are no
  sections available for review.

  If the user successfully chooses a section, start going through all the 
  questions in that section, sorted by how important the question is.

  A question's importance, or priority, is stored alongside the question in
  the section file. The default priority is 2. The priority may go up to 1
  if the user reacts with the green symbol, or go down to 3 if the user 
  reacts with the red symbol. If the user reacts with the yellow symbol,
  the question's priority remains the same.

  After going through all the questions, the user may type "continue" to
  go through all the questions again. If not, the user may choose to go 
  through the questions they reacted red to again by replying "yes."

  The updated priorities are written into the same section after excecution
  of this function.
  """
  p = get_default_path(member)
  preferences = await load_preferences(member, channel)
  timeout = preferences["timeout"]
  color = preferences["color"]

  if not p.exists() or sum([1 for f in p.iterdir()]) == 0:
    embed=discord.Embed(title="You have no flashcards!", description="use \"!flashcards add\" to add some!", color=color)
    await channel.send(embed=embed)
    return
  prefix = "flashcards\\" + str(member.id) + "\\"
  
  embed=discord.Embed(title="Available flashcards:", color=color)
  for path in p.iterdir():
    name = str(path).removeprefix(prefix)[:-5]
    last_modified = datetime.datetime.fromtimestamp(path.stat().st_ctime)
    embed.add_field(name=name, value=last_modified, inline=False)
  await channel.send(embed=embed)

  def check(m):
    return m.author == member and m.channel == channel
  
  try:
    selection = await client.wait_for('message', check=check, timeout=timeout)
  except asyncio.exceptions.TimeoutError:
    return
  selection = selection.content

  if (selection == exit):
    return

  p = p / (selection + ".json")
  if not p.exists():
    embed=discord.Embed(title="Invalid Selection", color=color)
    await channel.send(embed=embed)
    study(client, member, channel)
  
  data = None
  with p.open("r") as f:
    data = json.load(f)

  data = sorted(data, key=lambda x: x["priority"])
  
  def reaction_check(reaction, user):
    return user == member and (str(reaction.emoji) == '🟢' or str(reaction.emoji) == '🟡' or str(reaction.emoji) == '🔴')

  next = []
  cont = 1
  while cont:
    for question in data:
      embed=discord.Embed(title="Question: " + question["question"], color=color)
      await channel.send(embed=embed)
      try:
        question_response = await client.wait_for('message', check=check)
      except asyncio.exceptions.TimeoutError:
        return

      question_response = question_response.content
      if question_response == "stop":
        return
        
      embed=discord.Embed(title="Expected Answer: " + question["answer"], color=color)
      sent_message = await channel.send(embed=embed)
      await sent_message.add_reaction('🔴')
      await sent_message.add_reaction('🟡')
      await sent_message.add_reaction('🟢')
      try:
        reaction = await client.wait_for('reaction_add', check=reaction_check, timeout=timeout)
      except asyncio.exceptions.TimeoutError:
        return
      reaction = reaction[0].emoji
      if reaction == '🔴':
        question["priority"] = max(question["priority"] - 1, 1)
        next.append(question)
      if reaction == '🟢':
        question["priority"] = min(question["priority"] + 1, 3)
    
    embed=discord.Embed(title="End of flashcards in " + selection + ".", description="Type \"continue\" to start again.", color=color)
    await channel.send(embed=embed)
    try:
      reply = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    reply = reply.content.lower()
    if reply != "continue":
      cont = 0

  if len(next) > 0:
    embed=discord.Embed(title="Go through hard questions again?" , description="Type \"yes\" to proceed.", color=color)
    await channel.send(embed=embed)
    try:
      message = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    message = message.content.lower()
    if message == "yes":
      for question in next:
        embed=discord.Embed(title="Question: " + question["question"], color=color)
        await channel.send(embed=embed)
        try:
          question_response = await client.wait_for('message', check=check, timeout=timeout)
        except asyncio.exceptions.TimeoutError:
          return
        question_response = question_response.content
        if question_response == "stop":
          return

        embed=discord.Embed(title="Expected Answer: " + question["answer"], color=color)
        sent_message = await channel.send(embed=embed)
        await sent_message.add_reaction('🔴')
        await sent_message.add_reaction('🟡')
        await sent_message.add_reaction('🟢')
        try:
          reaction = await client.wait_for('reaction_add', check=reaction_check, timeout=timeout)
        except asyncio.exceptions.TimeoutError:
          return
        reaction = reaction[0].emoji
        if reaction == '🔴':
          question["priority"] = max(question["priority"] - 1, 1)
        if reaction == '🟢':
          question["priority"] = min(question["priority"] + 1, 3)

  with p.open("w") as f:
    data = json.dump(data, f)
  

async def add(client, member, channel):
  """
  Adds a new section for the user to review in the future, if the provided 
  name is unique. Otherwise, the new content is appended to the end of the
  existing section.

  A section's name cannot contain characters not allowed in filenames.

  The user is prompted for questions and answers to be added into the 
  section. The default priority for every question is 2. This will be 
  repeated until the user enters "stop" on a question prompt. If the answer
  entered one or more questions in this period, the questions and answers
  are written into the section's file.
  """
  p = get_default_path(member)
  p.mkdir(parents=True, exist_ok=True)
  preferences = await load_preferences(member, channel)
  timeout = preferences["timeout"]
  color = preferences["color"]

  def check(m):
    return m.author == member and m.channel == channel

  embed=discord.Embed(title="Enter category name:", color=color)
  await channel.send(embed=embed)

  try:
    name = await client.wait_for('message', check=check, timeout=timeout)
  except asyncio.exceptions.TimeoutError:
    return
  name = name.content
  name = name.replace("<", "").replace(">", "").replace(":", "").replace("\"", "").replace("/", "").replace("\\", "").replace("|", "").replace("?", "").replace("*", "")
  # name.replace(" ", "_")

  output = []
  while 1:
    embed=discord.Embed(title="Please enter a question:", description="\"stop\" to exit", color=color)
    await channel.send(embed=embed)
    try:
      question = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    question = question.content
    
    if question == "stop":
      break

    embed=discord.Embed(title="Please enter an answer:", color=color)
    await channel.send(embed=embed)
    try:
      answer = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    answer = answer.content
    current = {}
    current["question"] = question
    current["answer"] = answer
    current["priority"] = 2
    output.append(current)

  if len(output) > 0:
    p = p / (name + ".json")
    with p.open("a") as f:
      json.dump(output, f)
    embed=discord.Embed(title="Category " + name + " added.", color=color)
    await channel.send(embed=embed)

async def remove(client, member, channel):
  def check(m):
    return m.author == member and m.channel == channel

  preferences = await load_preferences(member, channel)
  timeout = preferences["timeout"]
  color = preferences["color"]

  embed=discord.Embed(title="Please enter an item to remove", color=color)
  embed.add_field(name="Question", value="Remove a question from a section", inline=False)
  embed.add_field(name="Section", value="Remove an entire section", inline=False)
  await channel.send(embed=embed)
  try:
    selection = await client.wait_for('message', check=check)
  except asyncio.exceptions.TimeoutError:
    return
  selection = selection.content
  if selection == "stop":
    return
  elif selection == "question":
    p = get_default_path(member)
    section = await get_options(client, member, channel)
    if section == -1:
      return
    p = p / section
    data = None
    with p.open("r") as f:
      data = json.load(f)
    embed=discord.Embed(title="Please enter the question")
    await channel.send(embed=embed)
    try:
      question = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    question = question.content
    for i in range(len(data)):
      if data[i]["question"] == question:
        data.pop(i)
    with p.open("w") as f:
      data = json.dump(data, f)
    embed=discord.Embed(title="Question " + question + " removed.", color=color)
    await channel.send(embed=embed)
    return
  elif selection == "section":
    p = get_default_path(member)
    section = await get_options(client, member, channel)
    p = p / section
    try:
      p.unlink()
    except:
      pass
    embed=discord.Embed(title="Section " + section[:-5] + " removed.", color=color)
    await channel.send(embed=embed)
    return
  else:
    embed=discord.Embed(title="Invalid option.", description="Type \"stop\" to exit.", color=color)
    await channel.send(embed=embed)
    await remove(client, member, channel)

async def change_preferences(client, member, channel):
  """
  Allows for the timeout for interactions and color of the embed to be 
  changed per user.
  
  Upon calling this function, the user is asked whether they would like to 
  change their color or their timeout.

  If the user chooses "color," they are prompted for a hexadecimal 
  representation for a color. The default color is "0x6bb3ff."

  If the user chooses "timeout," they are prompted for an integer
  representing the new timeout they would like. The default timeout is 15
  seconds.
  """
  def check(m):
    return m.author == member and m.channel == channel

  p = pathlib.Path("config/" + str(member.id) + ".json")
  preferences = await load_preferences(member, channel)
  color = preferences["color"]
  timeout = preferences["timeout"]

  embed=discord.Embed(title="Enter the preference you would like to change", color=color)
  embed.add_field(name="Color", value="Change the embed color", inline=False)
  embed.add_field(name="Timeout", value="Change the amount of time you have to respond to questions", inline=False)
  await channel.send(embed=embed)
  try:
    selection = await client.wait_for('message', check=check, timeout=timeout)
  except asyncio.exceptions.TimeoutError:
    return
  selection = selection.content.lower()

  if selection == "color":
    embed=discord.Embed(title="Enter your new color (0x6bb3ff by default)", description="Current color is " + str(hex(color)), color=color)
    await channel.send(embed=embed)
    try:
      new_color = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    new_color = int(new_color.content, 16)
    preferences["color"] = new_color
    embed=discord.Embed(title="Your new color is " + str(hex(new_color)), color=new_color)
    await channel.send(embed=embed)
  elif selection == "timeout":
    embed=discord.Embed(title="Enter your new timeout (15s default)", description="Current timeout is " + str(timeout), color=color)
    await channel.send(embed=embed)
    try:
      new_timeout = await client.wait_for('message', check=check, timeout=timeout)
    except asyncio.exceptions.TimeoutError:
      return
    try:
      new_timeout = int(new_timeout.content)
    except:
      embed=discord.Embed(title="Invalid timeout", color=color)
      await channel.send(embed=embed)
      return
    preferences["timeout"] = new_timeout
    embed=discord.Embed(title="Your new timeout is " + str(new_timeout), color=color)
    await channel.send(embed=embed)
  else:
    embed=discord.Embed(title="Invalid Option", color=color)
    await channel.send(embed=embed)
    return
  with p.open("w") as f:
    json.dump(preferences, f)

def get_default_path(member):
  return pathlib.Path("flashcards/" + str(member.id))

async def get_options(client, member, channel):
  """
  Lists the available sections for the passed user. Return their selection.
  """
  p = get_default_path(member)

  preferences = await load_preferences(member, channel)
  timeout = preferences["timeout"]
  color = preferences["color"]

  if not p.exists() or sum([1 for f in p.iterdir()]) == 0:
    embed=discord.Embed(title="You have no flashcards!", color=color)
    await channel.send(embed=embed)
    return -1
  prefix = "flashcards\\" + str(member.id) + "\\"
  
  embed=discord.Embed(title="Available flashcards:", description="Type \"stop\" to exit", color=color)
  for path in p.iterdir():
    name = str(path).removeprefix(prefix)[:-5]
    last_modified = datetime.datetime.fromtimestamp(path.stat().st_ctime)
    embed.add_field(name=name, value=last_modified, inline=False)
  await channel.send(embed=embed)

  def check(m):
    return m.author == member and m.channel == channel

  try:
    selection = await client.wait_for('message', check=check, timeout=timeout)
  except asyncio.exceptions.TimeoutError:
    return
  return selection.content + ".json"

async def load_preferences(member, channel):
  """
  Load the preferences belonging to the current user, if it exists. Otherwise,
  create a new preference file which is named the ID of the user.

  The available preferences are timeout and color.
  """
  p = pathlib.Path("config/" + str(member.id) + ".json")
  if p.exists():
    with p.open("r") as f:
      result = json.load(f)
      return result
  else:
    settings = {}
    settings["timeout"] = 15
    settings["color"] = 0x6bb3ff
    with p.open("w") as f:
      json.dump(settings, f)
    return settings

async def help(member, channel):
  """
  Sends a message with the descriptions for different commands.
  """
  embed=discord.Embed(title="This is the help section for flashcards", description="Type \"stop\" to stop in any submenus", color=0x6bb3ff)
  embed.add_field(name="Add", value="Make a new study section or append to a current study section", inline=False)
  embed.add_field(name="Study", value="Review flashcards in a study section", inline=False)
  embed.add_field(name="Remove", value="Remove either a section or a question from a sesction", inline=False)
  embed.add_field(name="Change Preferences", value="Change either color or timeout", inline=False)
  await channel.send(embed=embed)
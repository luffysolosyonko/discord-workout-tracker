import os
import json
from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import matplotlib.pyplot as plt


# Discord setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='.', intents=intents)

# Firebase setup
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def estimate_calories(exercise, sets, reps, weight, body_weight=160):
    met_table = {
        "squat": 6.0, "bench": 3.5, "deadlift": 7.0, "pullup": 5.0, "running": 9.8
    }
    met = met_table.get(exercise.lower(), 5.0)
    duration = sets * 0.5
    return round((met * 3.5 * body_weight / 200) * duration, 1)

def create_progress_chart(entries, exercise):
    dates, weights = [], []
    for e in entries:
        if e["exercise"].lower() == exercise.lower():
            dates.append(e["timestamp"][:10])
            weights.append(e["weight"])

    if not weights:
        return None

    plt.figure()
    plt.plot(dates, weights, marker="o")
    plt.title(f"{exercise.capitalize()} Progress")
    plt.xlabel("Date")
    plt.ylabel("Weight (lbs)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    filename = f"{exercise}_progress.png"
    plt.savefig(filename)
    plt.close()
    return filename

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")

@bot.command(name="log")
async def log_workout(ctx, exercise: str, sets: int, reps: int, weight: int):
    user_id = str(ctx.author.id)
    doc_ref = db.collection("workouts").document(user_id)
    timestamp = datetime.now().isoformat()
    calories = estimate_calories(exercise, sets, reps, weight)

    workout = {
        "exercise": exercise,
        "sets": sets,
        "reps": reps,
        "weight": weight,
        "calories": calories,
        "timestamp": timestamp
    }

    doc = doc_ref.get()
    history = doc.to_dict().get("entries", []) if doc.exists else []
    history.append(workout)
    doc_ref.set({"entries": history})
    await ctx.send(f"✅ Logged `{exercise}` {sets}x{reps} @ {weight} lbs\n🔥 {calories} kcal burned")

@bot.command(name="history")
async def workout_history(ctx):
    user_id = str(ctx.author.id)
    doc = db.collection("workouts").document(user_id).get()

    if not doc.exists:
        await ctx.send("❌ No workout history found.")
        return

    entries = doc.to_dict().get("entries", [])
    if not entries:
        await ctx.send("❌ No workout data.")
        return

    msg = "\n".join(
        [f"{i+1}. {e['timestamp'][:10]}: {e['exercise']} {e['sets']}x{e['reps']} @ {e['weight']} lbs"
         for i, e in enumerate(entries[-10:])]
    )

    await ctx.send(f"📜 Your last 10 workouts:\n```\n{msg}\n```")

@bot.command(name="delete")
async def delete_workout(ctx, number: int):
    user_id = str(ctx.author.id)
    doc_ref = db.collection("workouts").document(user_id)
    doc = doc_ref.get()

    if not doc.exists:
        await ctx.send("❌ No workouts to delete.")
        return

    entries = doc.to_dict().get("entries", [])

    if number < 1 or number > len(entries):
        await ctx.send("❌ Invalid number.")
        return

    removed = entries.pop(number - 1)
    doc_ref.set({"entries": entries})

    await ctx.send(f"🗑️ Deleted entry #{number}: `{removed['exercise']} {removed['sets']}x{removed['reps']} @ {removed['weight']} lbs`")

@bot.command(name="edit")
async def edit_workout(ctx, number: int, exercise: str, sets: int, reps: int, weight: int):
    user_id = str(ctx.author.id)
    doc_ref = db.collection("workouts").document(user_id)
    doc = doc_ref.get()

    if not doc.exists:
        await ctx.send("❌ No workouts to edit.")
        return

    entries = doc.to_dict().get("entries", [])

    if number < 1 or number > len(entries):
        await ctx.send("❌ Invalid entry number.")
        return

    old = entries[number - 1]
    entries[number - 1] = {
        "exercise": exercise,
        "sets": sets,
        "reps": reps,
        "weight": weight,
        "calories": estimate_calories(exercise, sets, reps, weight),
        "timestamp": old["timestamp"]  # keep original timestamp
    }

    doc_ref.set({"entries": entries})
    await ctx.send(f"✅ Updated entry #{number}: `{exercise} {sets}x{reps} @ {weight} lbs`")


@bot.command(name="compare")
async def compare_last(ctx, exercise: str):
    user_id = str(ctx.author.id)
    doc = db.collection("workouts").document(user_id).get()
    entries = [e for e in doc.to_dict().get("entries", []) if e["exercise"].lower() == exercise.lower()]

    if len(entries) < 2:
        await ctx.send("Need at least 2 logs.")
        return

    prev, last = entries[-2], entries[-1]
    diff = last["weight"] - prev["weight"]
    symbol = "⬆️" if diff > 0 else "⬇️" if diff < 0 else "➡️"
    await ctx.send(f"{exercise.title()} Progress: {prev['weight']} → {last['weight']} lbs ({symbol} {abs(diff)} lbs)")

@bot.command(name="progress")
async def show_graph(ctx, exercise: str):
    user_id = str(ctx.author.id)
    doc = db.collection("workouts").document(user_id).get()
    entries = doc.to_dict().get("entries", []) if doc.exists else []
    path = create_progress_chart(entries, exercise)

    if path:
        await ctx.send(file=discord.File(path))
        os.remove(path)
    else:
        await ctx.send("❌ No data to plot.")
print("TOKEN:", os.getenv("DISCORD_TOKEN"))

@bot.command(name="undo")
async def undo_last(ctx):
    user_id = str(ctx.author.id)
    doc_ref = db.collection("workouts").document(user_id)
    doc = doc_ref.get()

    if not doc.exists:
        await ctx.send("❌ No workouts to undo.")
        return

    entries = doc.to_dict().get("entries", [])
    if not entries:
        await ctx.send("❌ Your log is empty.")
        return

    removed = entries.pop()
    doc_ref.set({"entries": entries})
    await ctx.send(f"↩️ Undid last workout: `{removed['exercise']} {removed['sets']}x{removed['reps']} @ {removed['weight']} lbs`")


bot.run(os.getenv("DISCORD_TOKEN"))

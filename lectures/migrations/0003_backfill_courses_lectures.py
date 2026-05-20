from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Course = apps.get_model("lectures", "Course")
    Lecture = apps.get_model("lectures", "Lecture")
    Audio = apps.get_model("lectures", "Audio")
    Document = apps.get_model("lectures", "Document")

    for user in User.objects.all():
        audios = Audio.objects.filter(user_id=user.id, lecture__isnull=True)
        if not audios.exists():
            continue
        course = Course.objects.create(user_id=user.id, title="Imported course")
        for audio in audios:
            lecture = Lecture.objects.create(
                course_id=course.id, title=audio.title, primary_audio_id=audio.id
            )
            audio.lecture_id = lecture.id
            audio.save(update_fields=["lecture"])
            Document.objects.filter(audio_id=audio.id, lecture__isnull=True).update(
                lecture_id=lecture.id
            )


def backwards(apps, schema_editor):
    Lecture = apps.get_model("lectures", "Lecture")
    Course = apps.get_model("lectures", "Course")

    Lecture.objects.all().delete()
    Course.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("lectures", "0002_course_lecture_flashcard_audio_lecture_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

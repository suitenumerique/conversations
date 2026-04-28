from django.db import migrations, models


def reset_smart_web_search_to_false(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(allow_smart_web_search=True).update(allow_smart_web_search=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_siteconfiguration"),
    ]

    operations = [
        migrations.RunPython(
            reset_smart_web_search_to_false,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="user",
            name="allow_smart_web_search",
            field=models.BooleanField(
                default=False,
                help_text="Whether the user allows to use smart web search features.",
                verbose_name="allow smart web search",
            ),
        ),
    ]

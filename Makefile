.PHONY: r mig mi shell deli numi user numu inin delu delca searcheck taste

r:
	python manage.py runserver
mig:
	python manage.py makemigrations
mi:
	python manage.py migrate
shell:
	python manage.py shell_plus
deli:
	python manage.py runscript reset_interactions
numi:
	python manage.py runscript count_interactions
user:
	python manage.py runscript make_demo_user --script-args "$(a)"
numu:
	python manage.py runscript count_demo_user
inin:
	python manage.py runscript insert_interactions --script-args "$(a)" "$(b)"
delu:
	python manage.py runscript reset_demo_user
delca:
	python manage.py runscript reset_cache
searcheck:
	python manage.py runscript check_search_score --script-args "$(a)" "$(b)"
taste:
	python manage.py update_user_taste

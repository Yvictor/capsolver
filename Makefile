image:
	docker build -t capsolver-api .

run:
	docker run --restart always --name capsolver-api --env-file ./.env -d -p 9987:9987 capsolver-api

stop:
	docker stop capsolver-api

remove:
	docker rm -f capsolver-api

clean: remove
	docker rmi -f capsolver-api

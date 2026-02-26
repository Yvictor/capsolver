image:
	docker build -t capsolver-api .

image-ext:
	docker build -t capsolver-api -f Dockerfile.ext .

run:
	docker run --restart always --name capsolver-api --env-file ./.env -d -p 9987:9987 \
		--label autoheal=true \
		capsolver-api

autoheal:
	docker run -d --name autoheal --restart always \
		-e AUTOHEAL_CONTAINER_LABEL=autoheal \
		-e AUTOHEAL_INTERVAL=30 \
		-v /var/run/docker.sock:/var/run/docker.sock \
		willfarrell/autoheal

stop:
	docker stop capsolver-api

remove:
	docker rm -f capsolver-api

clean: remove
	docker rmi -f capsolver-api

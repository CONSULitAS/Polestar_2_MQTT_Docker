# How to Configure a Docker Container for Synology

With Synology's interface, Docker automatically generates a `docker-compose.yml` in the background when setting up a container (see [Erstellen eines Containers | Docker - Synology Knowledge Center](https://kb.synology.com/de-de/DSM/help/Docker/docker_container?version=6)). 

To ensure the correct configuration for this specific container, you need to input the appropriate data into the Synology UI for the desired result.

## Steps to Configure the Container

1. **Download the Docker Image**
   Pull the image `consulitas/polestar_2_mqtt_docker:latest` from the Docker registry.

2. **Set the Environment Variables**
   - Go to the **Advanced Settings** of the container configuration in the Synology UI.
   - Navigate to the **Environment** tab (refer to the linked guide above for detailed instructions).
   - Enter the following variables in the Synology UI. Adjust the values to suit your requirements.

   | Name             | Value              | Comment                                  |
   |------------------|--------------------|------------------------------------------|
   | TZ               | Europe/Berlin      | Timezone                                 |
   | POLESTAR_EMAIL   | xx@xxx             | Replace with your email                  |
   | POLESTAR_PASSWORD| XXX                | Replace with your password               |
   | POLESTAR_VIN     | LPSVSEDEEMLxxxxxx  | Replace with your vehicle's VIN          |
   | POLESTAR_CYCLE   | 300                | Interval in seconds                      |
   | MQTT_BROKER      | 192.168.1.100      | Broker IP address                        |
   | MQTT_PORT        | 1883               | Broker port                              |
   | MQTT_USER        |                    | Leave empty if no user is required       |
   | MQTT_PASSWORD    |                    | Leave empty if no password is required   |
   | MQTT_BASE_TOPIC  | polestar2          | Base MQTT topic                          |

3. **Ignore Additional Settings**
   - You **do not need to configure** volumes, networks, ports, or links for this container.

## Notes
- Ensure to adapt the placeholder values (`xx@xxx`, `XXX`, etc.) to match your personal credentials and environment.
- After configuration, the container should run on Synology without issues.

Happy configuring!

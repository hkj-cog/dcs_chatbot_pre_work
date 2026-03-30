## setup pubsub emulator locally for testing

1.  execute this command to start the emulator: `gcloud beta emulators pubsub start --project=emulator-project --host-port=localhost:8406`
2.  then set the environment variable to point to the emulator: `export PUBSUB_EMULATOR_HOST=localhost:8406`
3.  then execute the @setup_pubsub_emulator function in the test file

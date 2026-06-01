# L7R Combat Simulator

## Live site

This can be found at https://l7r-character-sheet.fly.dev/

## Development

```
podman run --interactive --tty --rm \
    --name character-sheet \
    --uidmap 0:1:1000 \
    --uidmap 1000:0:1 \
    --uidmap 1001:1001:64536 \
    --gidmap 0:1:1000 \
    --gidmap 1000:0:1 \
    --gidmap 1001:1001:64536 \
    --env HOME=/home/agent \
    --volume "$(pwd)":/workspace:Z \
    --volume /home/eli/l7r:/host-l7r-repo:Z \
    --volume "$HOME/.claude":/home/agent/.claude:z \
    --volume "$HOME/.claude.json":/home/agent/.claude.json:z \
    --workdir /workspace \
    --memory 8g \
    --memory-swap 8G \
    docker.io/docker/sandbox-templates:claude-code \
    bash
```

## Backlog

- initiative freeform edits
- award money button on the group page for the GM to use
- smarter action die spending, e.g. schools that can take interrupt actions for the cost of 1 action die
- ide diplomat feint temp vp vs 5th dan temp vp
- priest 3rd dan freeform edits and interaction with custom modals (Kakita 5th dan attacks, Dragon tattoo rolls, etc)
- should parry also get a probability chart?  (for parry schools, probably so, but no one has one of those in the current campaign)
- headshot not automatically selected on image upload
- doesn't warn you about art generation overriding what you've already got saved
- verify the old images are deleted
- opponent made a failed parry roll should have an option for "someone made a failed parry roll for them"
- player character points
- dark mode
- arbitrary image art on Freeform sections, both uploaded and generated (and maybe inline as well?) and backed up to S3 like the headshots already are
- Shadowlands taint section
- between places
- spirit encounters
- mass combat
- professions (bleh)
- import feature improvements: test with real world sheets from past campaigns, have it use live creds to do real end-to-end testing, but with careful gatekeeping to ensure we don't spend money on every subsequent unit test run after that point


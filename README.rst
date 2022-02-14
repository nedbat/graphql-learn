An opportunity to learn more about GraphQL.

There are two programs here:

- openedx_repos.py

  Enumerates repos with openedx.yaml files to find repos to tag for Open edX
  releases.  Doing this with the REST API takes about a minute. Using GraphQL
  takes about six seconds.

- issues.py

  Examines repos and projects, producing a report of changes since a certain
  date.  Makes a "daily digest" of activity across a number of issue
  containers.  Has some code to start looking at pull requests too, but that's
  much more complicated.

  Currently the parameters are hard-coded while we continue hacking on it.

  An example report is at https://nedbat.github.io/graphql-learn/example.html

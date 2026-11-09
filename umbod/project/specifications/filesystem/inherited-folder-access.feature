Feature: Folder sharing follows explicit scope and current ancestry
  Folder shares include existing and future contents by default.
  Direct grants and inherited grants add permissions together.
  Ownership remains local to the owned item.

  Background:
    Given Alice owns the folder "Projects"
    And "Projects" contains the file "Brief.txt"
    And "Projects" contains the folder "Design"
    And "Design" contains the file "Notes.txt"
    And every referenced item has valid ownership
    And Bob has no permissions except those stated

  Scenario: New folder sharing includes existing descendants by default
    When Alice shares "Projects" with Bob using Discover and Read
    Then the grant on "Projects" includes its contents
    And Bob can browse "Projects" and "Design"
    And Bob can read "Brief.txt" and "Notes.txt"
    And Bob cannot write, delete, or share those items
    And no grants are copied onto descendants

  Scenario: Newly created files inherit the current folder share
    Given Bob has Discover and Read on "Projects" including its contents
    When Alice creates "Projects/Later.txt"
    Then Bob can discover and read "Later.txt"
    And "Later.txt" has no copied direct grants

  Scenario: Newly created nested folders inherit the current folder share
    Given Bob has Discover and Read on "Projects" including its contents
    When Alice creates "Projects/Research/Results.txt"
    Then Bob can browse "Research"
    And Bob can read "Results.txt"

  Scenario: Shares granted to groups are inherited
    Given Bob belongs to the group "Reviewers"
    When Alice shares "Projects" with "Reviewers" using Discover and Read including its contents
    Then Bob can read "Brief.txt" and "Notes.txt"

  Scenario: Group membership and issuer remain authorization boundaries
    Given "Reviewers" has Discover and Read on "Projects" including its contents
    When a caller has a similarly named group from another issuer
    Then that grant gives the caller no permissions on "Projects" or its contents

  Scenario: Nested ancestor grants add together
    Given Bob has Discover and Read on "Projects" including its contents
    And Bob has Write on "Design" including its contents
    Then Bob has Discover, Read, and Write on "Notes.txt"
    And Bob has only Discover and Read on "Brief.txt"

  Scenario: Direct write combines with inherited read
    Given Bob has Discover and Read on "Projects" including its contents
    And Bob has a direct Write grant on "Brief.txt"
    Then Bob has Discover, Read, and Write on "Brief.txt"

  Scenario: Direct read does not override inherited write
    Given Bob has Discover, Read, and Write on "Projects" including its contents
    And Bob has a direct Read grant on "Brief.txt"
    Then Bob can still write "Brief.txt"

  Scenario: Removing a direct grant retains inherited access
    Given Bob has Discover and Read on "Projects" including its contents
    And Bob has a direct Write grant on "Brief.txt"
    When Alice removes Bob's direct grant on "Brief.txt"
    Then Bob can still discover and read "Brief.txt"
    And Bob cannot write "Brief.txt"

  Scenario: Revoking a folder share removes its inherited contribution immediately
    Given Bob has Discover and Read on "Projects" including its contents
    When Alice revokes Bob's grant on "Projects"
    Then a fresh request cannot discover or read "Brief.txt" or "Notes.txt"
    And no descendant grant cleanup is required

  Scenario: Revoking inherited access does not revoke independent direct access
    Given Bob has Discover and Read on "Projects" including its contents
    And Bob has a direct Discover and Read grant on "Brief.txt"
    When Alice revokes Bob's grant on "Projects"
    Then Bob can still discover and read "Brief.txt"
    And Bob cannot discover "Notes.txt"

  Scenario: Folder ownership does not propagate
    Given Carol owns "Brief.txt"
    And Alice has no direct or inherited grants on "Brief.txt"
    Then owning "Projects" gives Alice no permissions on "Brief.txt"
    And Carol remains the owner of "Brief.txt"

  Scenario: Existing folder-only grants are not silently widened
    Given a stored Discover and Read grant on "Projects" for Bob has recursive set to false
    When inherited sharing is enabled
    Then Bob can discover "Projects"
    And that grant gives Bob no permissions on its contents
    And saving that grant without changing its scope preserves recursive set to false

  Scenario: Older clients preserve existing scope when they omit the scope field
    Given Bob has a stored folder-only Discover and Read grant on "Projects"
    When a client repeats or replaces Bob's grant without providing recursive
    Then Bob's grant remains folder-only
    And Bob gains no access to the contents
    And a new directory recipient with omitted scope defaults to including contents

  Scenario: Previously stored recursive grants are honored
    Given a stored Discover and Read grant on "Projects" for Bob has recursive set to true
    When Bob requests "Brief.txt"
    Then Bob can discover and read "Brief.txt"
    And no grant is copied onto "Brief.txt"

  Scenario: Folder-only sharing remains an explicit choice
    When Alice shares "Projects" with Bob using Discover and Read
    And Alice explicitly selects folder-only scope
    Then Bob can discover "Projects"
    And that grant gives Bob no permissions on its contents

  Scenario: Widening an existing folder-only share requires explicit saving
    Given Bob has a folder-only Discover and Read grant on "Projects"
    When Alice selects "Include contents" for Bob
    Then a warning states that existing and future contents will be shared
    And Bob has not yet gained access to the contents
    When Alice saves the changed scope
    Then Bob can read "Brief.txt" and "Notes.txt"
    And the operation reports a change even though the permission set is unchanged

  Scenario: Cancelling a scope change preserves the stored grant
    Given Bob has a folder-only Discover and Read grant on "Projects"
    When Alice selects "Include contents" for Bob
    And Alice cancels the sharing dialog
    Then Bob's grant remains folder-only
    And Bob gains no access to the contents

  Scenario: Repeating an identical recursive share is unchanged
    Given Bob has Discover and Read on "Projects" including its contents
    When Alice repeats that share with the same scope and permissions
    Then the operation reports no change

  Scenario: File shares remain direct
    When Alice shares "Brief.txt" with Bob using Discover and Read
    Then the stored file grant is direct-only
    And no inheritance setting implies that a file can contain children

  Scenario: Read does not implicitly grant discovery
    Given Bob has only Read on "Projects" including its contents
    Then Bob cannot browse "Projects"
    And Bob cannot download "Brief.txt" without Discover permission

  Scenario: Internal traversal does not expose hidden ancestors
    Given Bob has a direct Discover and Read grant on "Notes.txt"
    And Bob cannot discover "Projects" or "Design"
    Then Bob can inspect and read "Notes.txt"
    And its visible breadcrumbs do not reveal hidden ancestor names or identities

  Scenario: Corrupt ancestry cannot grant inherited authority
    Given Bob has no direct grant on "Brief.txt"
    And resolving its inherited policy encounters a missing, cyclic, or non-folder ancestor
    When Bob requests access through an ancestor grant
    Then access fails closed
    And no partially accumulated inherited permissions are returned

  Scenario: Authorization surfaces agree about inherited access
    Given Bob has Discover and Read on "Projects" including its contents
    Then file listing capabilities and caller permission status reflect inherited read access
    And MCP operation discovery includes the authorized filesystem operations
    And fresh operation authorization enforces the same permission rules

  Scenario: Root grants retain their explicit scope
    Given a stored root grant has recursive set to false
    Then that grant does not give access to personal homes
    When a root grant explicitly includes its contents
    Then its declared permissions apply to descendants including personal homes
    And no ownership or implicit home exception changes that scope

Feature: Moving items replaces inherited access and preserves direct sharing
  Inherited permissions follow the current folder hierarchy.
  Every cross-folder move receives a conservative access warning.
  The warning makes no claims about hidden recipients or precise access changes.

  Background:
    Given Alice is authorized to move the referenced item
    And Alice has Discover and Write on its current and destination folders
    And every referenced item has valid ownership

  Scenario: Moving into a shared folder adds its inherited permissions
    Given Bob has Discover and Read on "Shared" including its contents
    And Bob has no access to "Brief.txt" in "Private"
    When Alice confirms moving "Brief.txt" into "Shared"
    Then Bob can discover and read "Brief.txt"
    And no direct grants are added to "Brief.txt"

  Scenario: Moving out of a shared folder removes its inherited contribution
    Given Bob has Discover and Read on "Shared" including its contents
    And "Brief.txt" is in "Shared"
    And Bob has no independent access to "Brief.txt" or "Private"
    When Alice confirms moving "Brief.txt" into "Private"
    Then Bob cannot discover or read "Brief.txt"
    And no direct grants are removed from "Brief.txt"

  Scenario: Moving between shared folders replaces external inherited access
    Given Bob has Discover and Read on "Source" including its contents
    And Carol has Discover and Read on "Destination" including its contents
    And "Brief.txt" is in "Source"
    And Bob and Carol have no other grants on the file
    When Alice confirms moving "Brief.txt" into "Destination"
    Then Bob cannot discover or read "Brief.txt"
    And Carol can discover and read "Brief.txt"

  Scenario: Direct grants survive a move
    Given Bob has a direct Discover, Read, and Write grant on "Brief.txt"
    When Alice confirms moving "Brief.txt" between folders
    Then Bob's direct grant remains unchanged
    And Bob can still discover, read, and write "Brief.txt"
    And ownership and file content remain unchanged

  Scenario: Common ancestors continue contributing access
    Given "Source" and "Destination" are beneath "Projects"
    And Bob has Discover and Read on "Projects" including its contents
    When Alice confirms moving "Brief.txt" from "Source" to "Destination"
    Then Bob retains Discover and Read on "Brief.txt"

  Scenario: Moving a folder updates its entire subtree dynamically
    Given Bob has Discover and Read on "Source" including its contents
    And Carol has Discover and Read on "Destination" including its contents
    And "Source/Design" contains nested folders and files
    When Alice confirms moving "Design" into "Destination"
    Then its descendants lose permissions inherited only from "Source"
    And its descendants gain permissions inherited from "Destination"
    And no descendant policies are copied or rewritten

  Scenario: Grants within a moved subtree remain effective
    Given Bob has Discover and Read on "Design" including its contents
    And Bob has a direct Write grant on "Design/Notes.txt"
    When Alice confirms moving "Design" between folders
    Then Bob retains Discover and Read on every descendant of "Design"
    And Bob retains Write on "Notes.txt"
    And those grants remain unchanged

  Scenario: Losing inherited access does not roll back an authorized move
    Given Alice's access to "Brief.txt" comes only from "Source"
    And "Destination" does not grant Alice access to its contents
    When Alice confirms an otherwise authorized move of "Brief.txt" into "Destination"
    Then the move succeeds exactly once
    And the result reports Alice's post-move permissions without exposing unauthorized policy
    And Alice's cached file details and mutation controls are removed
    And the client does not retry the successful move

  Scenario Outline: Cross-folder moves warn before mutation
    Given Alice requests a move using <method>
    Then the UI warns "Moving this item may change inherited access. Direct sharing remains unchanged."
    And no move mutation has been sent
    When Alice confirms the move
    Then the move is submitted once with the expected node revision
    And the backend rechecks current authorization and hierarchy

    Examples:
      | method                 |
      | the move-folder picker |
      | native file drag       |

  Scenario Outline: Cancelling a move changes nothing
    Given Alice is reviewing a move using <method>
    When Alice cancels or presses Escape
    Then the item remains in its original folder
    And no move mutation is sent
    And cancellation is not announced as a failure
    And keyboard focus returns to an available control

    Examples:
      | method                 |
      | the move-folder picker |
      | native file drag       |

  Scenario: The conservative warning does not disclose the audience
    Given Alice cannot inspect some contributing folder policies
    When Alice reviews a cross-folder move
    Then the warning reveals no hidden owners, recipients, folder names, or audience counts
    And sharing-management permission is not required to see the warning

  Scenario: The generic warning remains truthful if folder sharing changes
    Given Alice is reviewing a cross-folder move
    When a relevant folder grant changes before confirmation
    Then the warning does not assert a previously calculated audience
    And execution uses current authorization and current ancestry

  Scenario: Renaming does not replace inherited access
    Given Bob has inherited access to "Brief.txt"
    When Alice renames "Brief.txt" without changing its parent
    Then Bob's inherited access remains unchanged
    And no move warning is required

  Scenario: Invalid destination and stale revision cannot bypass authorization
    Given Alice has reviewed a move warning
    When the destination becomes unauthorized or the expected node revision becomes stale
    Then the backend rejects the move without changing placement or grants
    And confirmation does not substitute for authorization

  Scenario: Navigating away invalidates pending move review
    Given Alice is reviewing a native drag move
    When Alice navigates away or the source view is disposed
    Then that pending review cannot submit a later mutation
    And returning to the view does not reopen the old review

  Scenario: Duplicate confirmation cannot move twice
    Given Alice is reviewing a cross-folder move
    When Alice activates confirmation more than once while the mutation is pending
    Then only one move mutation is sent

  Scenario: Root and cyclic moves remain forbidden
    When Alice attempts to move the root or move a folder into its own descendant
    Then the backend rejects the move
    And sharing scope and all direct grants remain unchanged

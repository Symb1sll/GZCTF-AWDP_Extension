using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GZCTF.Migrations
{
    /// <inheritdoc />
    public partial class AddAwdpSubmissionLedger : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "AwdpSubmissions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    GameId = table.Column<int>(type: "integer", nullable: false),
                    ChallengeId = table.Column<int>(type: "integer", nullable: false),
                    ParticipationId = table.Column<int>(type: "integer", nullable: false),
                    RunnerChallenge = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    PatchSha256 = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Patch = table.Column<byte[]>(type: "bytea", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    FinishedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    Status = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    Message = table.Column<string>(type: "character varying(1000)", maxLength: 1000, nullable: false),
                    FixScore = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AwdpSubmissions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_AwdpSubmissions_GameChallenges_ChallengeId",
                        column: x => x.ChallengeId,
                        principalTable: "GameChallenges",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_AwdpSubmissions_Games_GameId",
                        column: x => x.GameId,
                        principalTable: "Games",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_AwdpSubmissions_Participations_ParticipationId",
                        column: x => x.ParticipationId,
                        principalTable: "Participations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AwdpSubmissions_ChallengeId",
                table: "AwdpSubmissions",
                column: "ChallengeId");

            migrationBuilder.CreateIndex(
                name: "IX_AwdpSubmissions_GameId_ChallengeId_ParticipationId_CreatedAt",
                table: "AwdpSubmissions",
                columns: new[] { "GameId", "ChallengeId", "ParticipationId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_AwdpSubmissions_ParticipationId",
                table: "AwdpSubmissions",
                column: "ParticipationId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "AwdpSubmissions");
        }
    }
}

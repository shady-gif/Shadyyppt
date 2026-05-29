import assert from "node:assert/strict";
import test from "node:test";
import {
  patchAppPropertiesXml,
  patchContentTypesXml,
  patchPresentationRelationshipsXml,
  patchPresentationXml,
  patchSlideTextXml,
} from "../src-node/exporters/ooxml-patcher.js";

test("patches text in a slide shape by cNvPr id", () => {
  const xml = `<?xml version="1.0"?><p:sld xmlns:p="p" xmlns:a="a"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="7" name="Title"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Old title</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>`;
  const patched = patchSlideTextXml(xml, [{ slidePath: "ppt/slides/slide1.xml", elementId: "7", text: "New title" }]);
  assert.match(patched, /<a:t>New title<\/a:t>/);
  assert.doesNotMatch(patched, /Old title/);
});

test("reorders and removes slide ids in presentation.xml", () => {
  const xml = `<?xml version="1.0"?><p:presentation xmlns:p="p" xmlns:r="r"><p:sldIdLst><p:sldId id="256" r:id="rId6"/><p:sldId id="257" r:id="rId7"/><p:sldId id="258" r:id="rId8"/></p:sldIdLst></p:presentation>`;
  const patched = patchPresentationXml(xml, {
    slides: [
      { id: "258", relationshipId: "rId8" },
      { id: "256", relationshipId: "rId6" },
    ],
  });
  assert.ok(patched.indexOf('id="258"') < patched.indexOf('id="256"'));
  assert.doesNotMatch(patched, /id="257"/);
});

test("adds cloned slide ids to presentation.xml", () => {
  const xml = `<?xml version="1.0"?><p:presentation xmlns:p="p" xmlns:r="r"><p:sldIdLst><p:sldId id="256" r:id="rId6"/></p:sldIdLst></p:presentation>`;
  const patched = patchPresentationXml(xml, {
    slides: [
      { id: "256", relationshipId: "rId6" },
      { id: "266", relationshipId: "rId19" },
    ],
  });
  assert.match(patched, /id="266"/);
  assert.match(patched, /r:id="rId19"/);
});

test("removes deleted slide relationships only", () => {
  const xml = `<?xml version="1.0"?><Relationships xmlns="rel"><Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/><Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/><Relationship Id="rIdTheme" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>`;
  const patched = patchPresentationRelationshipsXml(xml, {
    slides: [{ id: "256", relationshipId: "rId6" }],
  });
  assert.match(patched, /rId6/);
  assert.match(patched, /rIdTheme/);
  assert.doesNotMatch(patched, /rId7/);
});

test("adds cloned slide relationships", () => {
  const xml = `<?xml version="1.0"?><Relationships xmlns="rel"><Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>`;
  const patched = patchPresentationRelationshipsXml(xml, {
    slides: [
      { id: "256", relationshipId: "rId6", path: "ppt/slides/slide1.xml" },
      { id: "266", relationshipId: "rId19", path: "ppt/slides/slide11.xml" },
    ],
  });
  assert.match(patched, /rId19/);
  assert.match(patched, /Target="slides\/slide11.xml"/);
});

test("adds missing slide content type overrides", () => {
  const xml = `<?xml version="1.0"?><Types xmlns="ct"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>`;
  const patched = patchContentTypesXml(xml, {
    slides: [
      { path: "ppt/slides/slide1.xml" },
      { path: "ppt/slides/slide11.xml" },
    ],
  });
  assert.match(patched, /PartName="\/ppt\/slides\/slide11.xml"/);
});

test("updates app slide count when present", () => {
  const xml = `<?xml version="1.0"?><Properties xmlns="props"><Slides>10</Slides></Properties>`;
  const patched = patchAppPropertiesXml(xml, { slides: [{}, {}, {}] });
  assert.match(patched, /<Slides>3<\/Slides>/);
});
